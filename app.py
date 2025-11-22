from flask import Flask, request, jsonify
import os
import threading
from datetime import datetime
from quiz_solver import QuizSolver
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Load configuration from environment variables
EXPECTED_SECRET = os.getenv("QUIZ_SECRET")
EXPECTED_EMAIL = os.getenv("QUIZ_EMAIL")

if not EXPECTED_SECRET:
    raise ValueError("QUIZ_SECRET not set in environment")
if not EXPECTED_EMAIL:
    raise ValueError("QUIZ_EMAIL not set in environment")

# Rest of the code...

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/quiz', methods=['POST'])
def handle_quiz():
    """Main endpoint to receive and process quiz tasks"""
    
    # Validate JSON payload
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400
    except Exception as e:
        return jsonify({"error": "Invalid JSON"}), 400
    
    # Extract required fields
    email = data.get('email')
    secret = data.get('secret')
    url = data.get('url')
    
    # Validate required fields
    if not all([email, secret, url]):
        return jsonify({"error": "Missing required fields: email, secret, url"}), 400
    
    # Verify secret
    if secret != EXPECTED_SECRET:
        return jsonify({"error": "Invalid secret"}), 403
    
    # Verify email
    if email != EXPECTED_EMAIL:
        return jsonify({"error": "Invalid email"}), 403
    
    # Start quiz solving in background thread (non-blocking)
    # The quiz has a 3-minute timeout, so we respond immediately
    # and process asynchronously
    solver = QuizSolver(email, secret, url)
    thread = threading.Thread(target=solver.solve_quiz_chain, daemon=True)
    thread.start()
    
    return jsonify({
        "status": "accepted",
        "message": "Quiz processing started",
        "url": url
    }), 200

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)