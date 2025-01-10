from flask import Blueprint, request, abort, current_app as app
from app.bot.dialogue_manager.models import ChatModel
from flask import jsonify

chat = Blueprint('bots', __name__, url_prefix='/bots/v1/')

@chat.route('/chat', methods=['POST'])
def api():
    """
    Endpoint to converse with the chatbot.
    Delegates the request processing to DialogueManager.

    :return: JSON response with the chatbot's reply and context.
    """
    request_json = request.get_json(silent=True)
    if not request_json:
        return abort(400, description="JSON payload is missing")

    try:
        chat_request = ChatModel.from_json(request_json)
        chat_response = app.dialogue_manager.process(chat_request)
        return jsonify(chat_response.to_json())
    except Exception as e:
        app.logger.error(f"Error processing request: {e}", exc_info=True)
        return abort(500, description=f"error : {e}")