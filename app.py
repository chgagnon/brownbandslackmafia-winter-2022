import secrets
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re

# usernames are received by the server as <123ABC>
USRNAME_PATTERN = "<.+>"
KILL_CMD_PREFIX = "kill "
KILL_PREFIX_LEN = len(KILL_CMD_PREFIX)
KILL_COMMAND = KILL_CMD_PREFIX + USRNAME_PATTERN

# Initializes your app with your bot token and socket mode handler
app = App(token=secrets.SLACK_BOT_TOKEN)

@app.event("app_mention")
def action_button_click(event, say):
    say(f"dude what do you want")

@app.message("hello")
def message_hello(message, say):
    # say() sends a message to the channel where the event was triggered
    say(f"Hey there <@{message['user']}>!")

@app.message(re.compile(KILL_COMMAND))
def message_kill(context, say):
    player_name = context['matches'][0][KILL_PREFIX_LEN:]
    if player_name == "diy-mafia-app":
        # this doesn't work because need to compare to bots internal user id
        # perform an api call to get that ID early on and store it somewhere
        say("You can't kill me you idiot")
    else:
        say(f"Fine I'll squash {player_name}")

@app.event("message")
def handle_message_events(body, logger):
    logger.info(body)
    print("received the following message:")
    print(body)

# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, secrets.SLACK_APP_TOKEN).start()