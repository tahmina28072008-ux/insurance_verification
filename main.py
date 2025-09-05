import json
import os
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# --- Firebase Initialization ---
# The __firebase_config and __app_id are global variables provided by the environment.
# We'll use them to initialize the Firebase Admin SDK.
firebase_config_str = os.getenv('__firebase_config', '{}')
firebase_config = json.loads(firebase_config_str)

# Ensure the app is only initialized once
if not firebase_admin._apps:
    try:
        # Check for service account credentials in the config
        if 'private_key' in firebase_config and 'client_email' in firebase_config:
            # Use a dictionary to create the credentials object
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
        else:
            # If no service account, try to initialize with the existing project ID
            firebase_admin.initialize_app()
    except Exception as e:
        print(f"Error initializing Firebase Admin SDK: {e}")

db = firestore.client()
app_id = os.getenv('__app_id', 'default-app-id')

# --- Webhook Route ---
@app.route('/verify-insurance', methods=['POST'])
def verify_insurance():
    """
    Handles Dialogflow webhook requests to verify insurance details against Firestore.
    """
    try:
        req = request.get_json(silent=True, force=True)
        print(json.dumps(req, indent=2))

        # Extract the parameters from the Dialogflow request
        parameters = req['fulfillmentInfo']['parameters']
        policy_number = parameters.get('policy_number', '')
        dob_str = parameters.get('date_of_birth', '')
        insurance_provider = parameters.get('insurance_provider', '')

        print(f"Received details: Policy Number={policy_number}, DOB={dob_str}, Provider={insurance_provider}")

        # --- Query Firestore for a matching patient ---
        # The Firestore collection path must follow the specified convention.
        patients_collection_ref = db.collection(f'artifacts/{app_id}/public/data/patients')

        # Create a query to find a matching patient document
        query = patients_collection_ref.where('policy_number', '==', policy_number) \
                                     .where('date_of_birth', '==', dob_str) \
                                     .where('insurance_provider', '==', insurance_provider)

        docs = list(query.stream())

        fulfillment_text = ""
        tag = ""

        if docs:
            # A matching document was found
            patient_data = docs[0].to_dict()
            name = patient_data.get('name', 'patient')
            fulfillment_text = f"Thank you, {name}, your insurance information has been verified."
            tag = "valid_code"
        else:
            # No matching document was found
            fulfillment_text = "I'm sorry, I could not find a match for that information. Please try again or speak with an agent."
            tag = "invalid_code"

        # --- Construct and return the Dialogflow webhook response ---
        response_json = {
            "fulfillmentResponse": {
                "messages": [
                    {
                        "text": {
                            "text": [fulfillment_text]
                        }
                    }
                ],
                "tag": tag
            }
        }
        return jsonify(response_json)

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({
            "fulfillmentResponse": {
                "messages": [
                    {
                        "text": {
                            "text": ["I'm sorry, an error occurred during verification."]
                        }
                    }
                ]
            }
        })

if __name__ == '__main__':
    # Add dummy data for local testing if running directly
    # To test this locally, you would need to set up Firebase authentication
    # and provide credentials via environment variables.
    print("This script is designed to run as a webhook. For local testing, ensure Firebase is configured.")
    app.run(port=5000, debug=True)
