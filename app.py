import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
import logging
from enum import Enum

class VoteType(Enum):
    PRAYER = 1
    KILL = 2

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
votes_by_target = {}
# dictionary with voting_player as keys
# values are single targeted player
votes_by_voter = {}

# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ.get('SLACK_BOT_TOKEN'), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

@app.event("app_mention")
def action_button_click(event, say):
    say("dude what do you want")

def translate_user_id_to_name(user_id):
    users_list = app.client.users_list(token=os.environ.get("SLACK_BOT_TOKEN"))
    for user in users_list['members']:
        if user['id'] == user_id:
            return user['real_name']
    return 'could not find a user name for this user ID'

def show_vote_results():
    print()
    print("VOTE TALLY UPDATE:")
    print()
    total_votes_cast_by_target = 0
    for target in votes_by_target.keys():
        num_votes_for_this_target = len(votes_by_target[target])
        target_str = "TARGET: " + str(target)
        numvotes_str = "| VOTES: " + str(num_votes_for_this_target)
        print(target_str.ljust(85) + numvotes_str.rjust(14))
        print("    voted by:")
        for voter in votes_by_target[target]:
            print("      " + voter, end=", ")
        total_votes_cast_by_target += num_votes_for_this_target
    
    total_votes_cast_by_voter = len(votes_by_voter.keys())
    
    if total_votes_cast_by_target == total_votes_cast_by_voter:
        print(f"\nVote count ({total_votes_cast_by_target}) by voter is equal count by target! Hooray!")
    else:
        print(f"Uh Oh. By target, total number of votes was {total_votes_cast_by_target} but by voter it was {total_votes_cast_by_voter}.")
    print("END TALLY UPDATE")
    print()

def update_vote_assignments(voter_user_id, target_name, vote_type):
    voter = translate_user_id_to_name(voter_user_id)
    
    # every player is really two targets
    # (one for prayers and one for kills)
    target = (target_name, vote_type)

    # previously cast a vote
    if voter in votes_by_voter.keys():
        old_target = votes_by_voter[voter]
        votes_by_target[old_target].remove(voter)
        assert(voter not in votes_by_target[old_target])

    # if voting_player NOT in votes_by_voter.keys(), then they
    # have not cast a vote today yet, so there's nothing to remove

    # add new vote
    votes_by_voter[voter] = target

    if target not in votes_by_target.keys():
        # make new list of voters for this target
        votes_by_target[target] = [voter]
    else:
        votes_by_target[target].append(voter)

def update_kill_vote(voting_player, target_player):
    update_vote_assignments(voting_player, target_player, VoteType.KILL) 
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
        # only 1 target can be specified - second case makes sure the regex match
        # contains only 1 user id
        if len(matches) == 1 and len(matches[0].split()) == 1:
            respond(f"<@{voting_player}> has voted to kill {user_to_kill}", response_type="in_channel")
            update_kill_vote(voting_player, user_to_kill)
        else:
            respond("Try again - you didn't specify a valid player.")

def update_prayer(praying_player, prayer_target):
    update_vote_assignments(praying_player, prayer_target, VoteType.PRAYER)
    show_vote_results()

@app.command("/prayto")
def handle_prayer(ack, respond, command):
    ack()
    prayer_targets = command['text'].split()
    praying_player = command['user_id']
    
    # no check for which channel because praying is allowed anywhere
    # check that only 1 user specified
    if len(prayer_targets) == 1: 
        respond(f"<@{praying_player}> is praying to {prayer_targets[0]}", response_type="in_channel")
        update_prayer(praying_player, prayer_targets[0])
    else:
        respond("Try again - you didn't specify a valid player.")

# Start your app
if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 3000)))
