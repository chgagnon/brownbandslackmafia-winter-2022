from os import kill
import secrets
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
import logging

logging.basicConfig(level=logging.INFO)

# usernames are received by the server as <123ABC>
USRNAME_PATTERN = "<.+>"
USRNAME_REGEX = re.compile(USRNAME_PATTERN)
KILL_CMD_PREFIX = "kill "
KILL_PREFIX_LEN = len(KILL_CMD_PREFIX)
KILL_COMMAND = KILL_CMD_PREFIX + USRNAME_PATTERN

MAIN_CHANNEL_NAME = "main_chat"

# global data that tracks voting results
# dictionary with target_player as keys
# values are list of voting players
kill_votes_by_target = {}
# dictionary with voting_player as keys
# values are single targeted player
kill_votes_by_voter = {}

# Initializes your app with your bot token and socket mode handler
app = App(token=secrets.SLACK_BOT_TOKEN)

@app.event("app_mention")
def action_button_click(event, say):
    say("dude what do you want")

def show_vote_results():
    print()
    print("VOTE TALLY UPDATE:")
    print()
    total_votes_cast_by_target = 0
    for target in kill_votes_by_target.keys():
        num_votes_for_this_target = len(kill_votes_by_target[target])
        print("TARGET:", target, " | VOTES:", num_votes_for_this_target)
        total_votes_cast_by_target += num_votes_for_this_target
    
    total_votes_cast_by_voter = len(kill_votes_by_voter.keys())
    
    if total_votes_cast_by_target == total_votes_cast_by_voter:
        print("Vote count by voter is equal count by target! Hooray!")
    else:
        print(f"Uh Oh. By target, total number of votes was {total_votes_cast_by_target} but by voter it was {total_votes_cast_by_voter}.")
    print("END TALLY UPDATE")
    print()

def update_kill_vote(voting_player, target_player):
    # previously cast a vote
    if voting_player in kill_votes_by_voter.keys():
        old_target = kill_votes_by_voter[voting_player]
        kill_votes_by_target[old_target].remove(voting_player)
        assert(voting_player not in kill_votes_by_target[old_target])

    # if voting_player NOT in kill_votes_by_voter.keys(), then they
    # have not cast a vote today yet, so there's nothing to remove
    # add them now
    kill_votes_by_voter[voting_player] = target_player

    if target_player not in kill_votes_by_target.keys():
        # make new list of voters for this target
        kill_votes_by_target[target_player] = [voting_player]
    else:
        kill_votes_by_target[target_player].append(voting_player)
    show_vote_results()

@app.command("/kill")
def handle_kill_vote(ack, respond, command):
    # Acknowledge command request
    ack()
    user_to_kill = command['text']
    voting_player = command['user_id']
    matches = USRNAME_REGEX.findall(user_to_kill)
    if command['channel_name'] != MAIN_CHANNEL_NAME: 
        respond("You can't do that in this channel.")
    else:
        if len(matches) == 1 and len(matches[0].split()) == 1:
            respond(f"<@{voting_player}> has voted to kill {user_to_kill}", response_type="in_channel")
            update_kill_vote(voting_player, user_to_kill)
        else:
            respond("Try again - you didn't specify a valid player.")

# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, secrets.SLACK_APP_TOKEN).start()