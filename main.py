# main.py
# A Flask application that handles Dialogflow webhook requests and
# connects to a Firestore database for patient data verification.

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- Firestore Connection Setup ---
try:
    # On Cloud Run, credentials are automatically provided by the environment.
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    logging.info("Firestore connected using Cloud Run environment credentials.")
except ValueError:
    # If running locally, you'll need a service account JSON file.
    # Set the 'GOOGLE_APPLICATION_CREDENTIALS' environment variable to its file path.
    try:
        cred = credentials.Certificate(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
        firebase_admin.initialize_app(cred)
        logging.info("Firestore connected using GOOGLE_APPLICATION_CREDENTIALS.")
    except Exception as e:
        logging.error(f"Error initializing Firebase: {e}")
        # To prevent the app from crashing, we'll continue, but database calls will fail.

db = firestore.client()

# --- Webhook Endpoint ---
@app.route('/')
def home():
    """Returns a simple message to confirm the service is running."""
    return "Webhook is running successfully!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handles POST requests from Dialogflow. It extracts patient information
    from the request and verifies it against the Firestore 'patients' collection.
    """
    logging.info("--- Webhook Request Received ---")
    req = request.get_json(force=True)
    
    # Log the full request JSON for debugging
    logging.info("Full Request JSON:")
    logging.info(json.dumps(req, indent=2))
    logging.info("-----------------------------------")

    # The Dialogflow CX webhook format has a different structure for parameters.
    # The parameters are nested inside 'sessionInfo'.
    session_info = req.get('sessionInfo', {})
    params = session_info.get('parameters', {})
    
    # Extract parameters based on your Dialogflow CX configuration.
    patient_policy_number = params.get('policy_number', '')
    patient_provider = params.get('insurance_provider_name', '')
    patient_dob_obj = params.get('date_of_birth', {})
    
    # Log the extracted parameters
    logging.info("Extracted Parameters:")
    logging.info(f"Policy Number: {patient_policy_number}")
    logging.info(f"Provider: {patient_provider}")
    logging.info(f"DOB Object: {patient_dob_obj}")
    logging.info("-----------------------------------")

    # Check if all required parameters are available.
    if not all([patient_policy_number, patient_provider, patient_dob_obj]):
        response_text = "Please provide your policy number, insurance provider, and date of birth to proceed with verification."
    else:
        # Correctly format the date of birth object into a 'YYYY-MM-DD' string.
        # This is the key change to handle the floating-point year from Dialogflow.
        dob_string = f"{int(patient_dob_obj.get('year'))}-{int(patient_dob_obj.get('month', 0)):02d}-{int(patient_dob_obj.get('day', 0)):02d}"

        # Call the function to query the database.
        response_text = verify_patient_insurance(
            patient_policy_number,
            patient_provider,
            dob_string
        )
    
    # Construct the final response in the format Dialogflow CX expects.
    dialogflow_response = {
        "fulfillmentResponse": {
            "messages": [
                {
                    "text": {
                        "text": [response_text]
                    }
                }
            ]
        }
    }
    
    # Log the response JSON before sending it
    logging.info("Final Dialogflow Response JSON:")
    logging.info(json.dumps(dialogflow_response, indent=2))
    logging.info("-----------------------------------")

    # Return the response to Dialogflow.
    return jsonify(dialogflow_response)

# --- Firestore Query Function ---
def verify_patient_insurance(policy_number, provider, dob):
    """
    Queries the Firestore 'patients' collection to find a matching document.
    """
    try:
        patients_ref = db.collection('patients')

        # Build the compound query with all criteria.
        query = patients_ref \
            .where('policyNumber', '==', policy_number) \
            .where('insuranceProvider', '==', provider) \
            .where('dateOfBirth', '==', dob)

        docs = query.stream()

        # Check if any documents were found.
        if any(docs):
            logging.info("Database match found. Verification successful.")
            return f"Thank you. Your insurance with {provider} and policy number {policy_number} has been verified."
        else:
            logging.info("No matching document found. Verification failed.")
            return "We could not find a patient with the information you provided. Please check your details and try again."
    except Exception as e:
        logging.error(f"Database query failed: {e}")
        return "Sorry, I am having trouble connecting to the database. Please try again later."

# --- Application Entry Point ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
