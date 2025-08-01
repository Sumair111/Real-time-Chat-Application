# backend/lambda_handler.py
import json
import os
from mangum import Mangum
from main import app

# Configure for Lambda environment
os.environ.setdefault('FIREBASE_DATABASE_URL', os.getenv('FIREBASE_DATABASE_URL'))

# Create Lambda handler
handler = Mangum(app, lifespan="off")

def lambda_handler(event, context):
    """
    AWS Lambda handler function
    """
    try:
        # Handle Firebase service account key
        if 'FIREBASE_SERVICE_ACCOUNT_KEY' in os.environ:
            service_account_key = json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT_KEY'])
            with open('/tmp/firebase-service-account.json', 'w') as f:
                json.dump(service_account_key, f)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/firebase-service-account.json'
        
        # Process the request
        response = handler(event, context)
        return response
        
    except Exception as e:
        print(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': True,
                'message': 'Internal server error',
                'details': str(e)
            })
        }