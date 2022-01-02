import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
import logging
from enum import Enum
import psycopg2

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
VOTE_RESULTS_CHANNEL_NAME = "vote-results"

PRAYER_STR = 'prayer'
KILL_STR = 'kill'

def test_database_connection():
    """ Connect to the PostgreSQL database server """
    conn = None
    try:
        # connect to the PostgreSQL server
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
        
        # create a cursor
        cur = conn.cursor()
        
    # execute a statement
        print('PostgreSQL database version:')
        cur.execute('SELECT version()')

        # display the PostgreSQL database server version
        db_version = cur.fetchone()
        print(db_version)
       
    # close the communication with the PostgreSQL
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()
            print('Database connection closed.')

def cast_vote_to_database(voter_id, target_name, vote_type):
    _, voter_name = translate_user_id_to_name(voter_id)

    # convert from Python enum to PostGres enum
    if vote_type == VoteType.KILL:
        vote_type = KILL_STR
    else:
        assert(vote_type == VoteType.PRAYER)
        vote_type = PRAYER_STR

    """ insert a new vote into the votes table """
    sql = """INSERT INTO votes(target_name, voter_name, vote_type)
             VALUES(%s, %s, %s)
             ON CONFLICT (voter_name)
             DO UPDATE
                SET target_name = excluded.target_name,
                    vote_type = excluded.vote_type,
                    votecast_time = excluded.votecast_time;"""
    conn = None
    try:
        # connect to the PostgreSQL database
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        # create a new cursor
        cur = conn.cursor()
        # execute the INSERT statement
        cur.execute(sql, (target_name, voter_name, vote_type))
        # commit the changes to the database
        conn.commit()
        # close communication with the database
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

def send_database_state_to_slack():
    slack_msg = "VOTE TALLY UPDATE:\n"

    for vote_type in [PRAYER_STR, KILL_STR]:
        slack_msg += f"for vote type: {vote_type}:\n"
        conn = None
        try:
            """ query data from the votes table """
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            cur = conn.cursor()
            cur.execute(f"SELECT target_name, COUNT(*) FROM votes WHERE vote_type = '{vote_type}' GROUP BY target_name ORDER BY COUNT(*)")
            print("The number of targets: ", cur.rowcount)
            row = cur.fetchone()

            while row is not None:
                target_str = f"TARGET: {row[0]}"
                numvotes_str = f"| VOTES: {row[1]}"
                slack_msg += target_str.ljust(85) + numvotes_str.rjust(14) + "\n"
                row = cur.fetchone()

            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
        finally:
            if conn is not None:
                conn.close()
    
    app.client.chat_postMessage(channel=VOTE_RESULTS_CHANNEL_NAME, text=slack_msg)

# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ.get('SLACK_BOT_TOKEN'), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

@app.event("app_mention")
def action_button_click(event, say):
    say("dude what do you want")

def translate_user_id_to_name(user_id):
    # token should be passed automatically
    # (specified token when initializing app)
    users_list = app.client.users_list()
    for user in users_list['members']:
        if user['id'] == user_id:
            return (user['id'], user['real_name'])
    return ('aw shucks', 'could not find a user name for this user ID')

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
    _, voter = translate_user_id_to_name(voter_user_id)
    
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
    # update_vote_assignments(voting_player, target_player, VoteType.KILL) 
    # show_vote_results()
    cast_vote_to_database(voting_player, target_player, VoteType.KILL)
    send_database_state_to_slack()

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
    # update_vote_assignments(praying_player, prayer_target, VoteType.PRAYER)
    # show_vote_results()
    cast_vote_to_database(praying_player, prayer_target, VoteType.PRAYER)
    send_database_state_to_slack()

@app.command("/prayto")
def handle_prayer(ack, respond, command):
    ack()
    prayer_targets = command['text'].split()
    praying_player = command['user_id']
    
    # no check for which channel because praying is allowed anywhere
    # check that only 1 user specified
    if len(prayer_targets) == 1: 
        uppercase_target = prayer_targets[0].upper()
        respond(f"<@{praying_player}> is praying to {uppercase_target}", response_type="in_channel")
        update_prayer(praying_player, uppercase_target)
    else:
        respond("Try again - you didn't specify a valid player.")

# Start your app
if __name__ == "__main__":
    # test_database_connection()
    app.start(port=int(os.environ.get("PORT", 3000)))
    print('started up the Bolt server')
