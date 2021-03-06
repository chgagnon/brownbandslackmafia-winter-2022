import os
from shutil import move
from tracemalloc import start
from urllib import response
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
import logging
from enum import Enum
import psycopg2


class VoteType(Enum):
    PRAYER = 1
    KILL = 2


class TicTacMove(Enum):
    OPEN = 1
    X = 2
    O = 3

    @staticmethod
    def get_opposite(e):
        if e == TicTacMove.X:
            return TicTacMove.O
        elif e == TicTacMove.O:
            return TicTacMove.X
        else:
            return TicTacMove.OPEN


logging.basicConfig(level=logging.INFO)

# usernames are received by the server as <123ABC>
USRNAME_PATTERN = "<.+>"
USRNAME_REGEX = re.compile(USRNAME_PATTERN)
KILL_CMD_PREFIX = "kill "
KILL_PREFIX_LEN = len(KILL_CMD_PREFIX)
KILL_COMMAND = KILL_CMD_PREFIX + USRNAME_PATTERN

MAIN_CHANNEL_NAME = "main_chat"
VOTE_RESULTS_CHANNEL_NAME = "vote-results"

PRAYER_STR = "prayer"
KILL_STR = "kill"

# for tic tac toe game
BOARD_HEIGHT = 3
BOARD_WIDTH = 3
# backticks escape Slack markdown formatting (by formatting as "code")
BLANK_BOARD_STR = "`_|_|_`\n`_|_|_`\n` | | `"
TIC_TAC_CHANNEL_NAMES = ["tic-tac-toe-test", "tic-tac-tolympics"]
TIE_STR = "TIE"


def test_database_connection():
    """Connect to the PostgreSQL database server"""
    conn = None
    try:
        # connect to the PostgreSQL server
        print("Connecting to the PostgreSQL database...")
        conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")

        # create a cursor
        cur = conn.cursor()

        # execute a statement
        print("PostgreSQL database version:")
        cur.execute("SELECT version()")

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
            print("Database connection closed.")


def cast_vote_to_database(voter_id, target_name, vote_type):
    voter_user_id, voter_name = translate_user_id_to_name(voter_id)

    # convert from Python enum to PostGres enum
    if vote_type == VoteType.KILL:
        vote_type = KILL_STR
    else:
        assert vote_type == VoteType.PRAYER
        vote_type = PRAYER_STR

    """ insert a new vote into the votes table """
    sql = """INSERT INTO votes(target_name, voter_name, vote_type, voter_user_id)
             VALUES(%s, %s, %s, %s)
             ON CONFLICT (voter_user_id)
             DO UPDATE
                SET target_name = excluded.target_name,
                    vote_type = excluded.vote_type,
                    votecast_time = excluded.votecast_time,
                    voter_user_id = excluded.voter_user_id,
                    voter_name = excluded.voter_name;"""
    conn = None
    try:
        # connect to the PostgreSQL database
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        # create a new cursor
        cur = conn.cursor()
        # execute the INSERT statement
        cur.execute(sql, (target_name, voter_name, vote_type, voter_user_id))
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
    slack_msg = "=======VOTE TALLY UPDATE=======\n"

    for vote_type in [PRAYER_STR, KILL_STR]:
        slack_msg += f"-------*for vote type {vote_type.upper()}*-------\n"
        conn = None
        try:
            """query data from the votes table"""
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            cur = conn.cursor()
            cur.execute(
                f"SELECT target_name, COUNT(*) as mycount, string_agg(voter_user_id, ', ') FROM votes WHERE vote_type = '{vote_type}' GROUP BY target_name ORDER BY mycount desc;"
            )

            print(
                f"Posting {vote_type.upper()} vote tally with total number of targets: ",
                cur.rowcount,
            )

            row = cur.fetchone()

            while row is not None:
                target_str = f"*TARGET:* {row[0]}"
                numvotes_str = f"| *VOTES:* {row[1]}"
                slack_msg += target_str.ljust(30) + numvotes_str.rjust(14) + "\n"
                user_id_list_str = ", ".join(
                    ["<@" + str(player_id) + ">" for player_id in row[2].split(", ")]
                )
                slack_msg += f"    _brought to you by_: {user_id_list_str}\n"
                row = cur.fetchone()

            cur.close()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
        finally:
            if conn is not None:
                conn.close()

    app.client.chat_postMessage(channel=VOTE_RESULTS_CHANNEL_NAME, text=slack_msg)


# Initializes your app with your bot token and socket mode handler
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


@app.event("app_mention")
def action_button_click(event, say):
    say("dude what do you want")


def translate_user_id_to_name(user_id):
    # token should be passed automatically
    # (specified token when initializing app)
    users_list = app.client.users_list()
    for user in users_list["members"]:
        if user["id"] == user_id:
            return (user["id"], user["real_name"])
    return ("aw shucks", "could not find a user name for this user ID")


def update_kill_vote(voting_player, target_player):
    # update_vote_assignments(voting_player, target_player, VoteType.KILL)
    # show_vote_results()
    cast_vote_to_database(voting_player, target_player, VoteType.KILL)
    send_database_state_to_slack()


@app.command("/kill")
def handle_kill_vote(ack, respond, command):
    # Acknowledge command request
    ack()
    user_to_kill = command["text"]
    voting_player = command["user_id"]
    matches = USRNAME_REGEX.findall(user_to_kill)
    if command["channel_name"] != MAIN_CHANNEL_NAME:
        respond("You can't do that in this channel.")
    else:
        # only 1 target can be specified - second case makes sure the regex match
        # contains only 1 user id
        if len(matches) == 1 and len(matches[0].split()) == 1:
            respond(
                f"<@{voting_player}> has voted to kill {user_to_kill}",
                response_type="in_channel",
            )
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
    prayer_targets = command["text"].split()
    praying_player = command["user_id"]

    # no check for which channel because praying is allowed anywhere
    # check that only 1 user specified
    if len(prayer_targets) == 1:
        uppercase_target = prayer_targets[0].upper()
        respond(
            f"<@{praying_player}> is praying to {uppercase_target}",
            response_type="in_channel",
        )
        update_prayer(praying_player, uppercase_target)
    else:
        respond("Try again - you didn't specify a valid player.")


@app.command("/tictacmove")
def handle_tictacmove(ack, respond, command):
    ack()
    if command["channel_name"] not in TIC_TAC_CHANNEL_NAMES:
        respond("You can't do that in this channel.")
    else:
        move_data = command["text"].split()
        if len(move_data) == 2:
            row_num = int(move_data[0])
            col_num = int(move_data[1])
            if (
                row_num >= 0
                and row_num < BOARD_HEIGHT
                and col_num >= 0
                and col_num < BOARD_WIDTH
            ):
                player = command["user_id"]
                make_tic_tac_toe_move(player, row_num, col_num, respond)
            else:
                respond(
                    "Try again - your move row and column were too large or too small."
                )
        else:
            respond("Try again - you didn't provide a move in proper format.")


# used for debugging the reset function - this slack command
# will be disabled before the app is put to use by the public
@app.command("/restart-tic-tac")
def handle_tic_tac_restart(ack, respond, command):
    ack()
    if command["channel_name"] not in TIC_TAC_CHANNEL_NAMES:
        respond("You can't do that in this channel.")
    else:
        reset_board_state()
        respond("Board should be reset now.")


@app.command("/tictacscoreboard")
def handle_tic_tac_scoreboard(ack, respond, command):
    ack()
    # allow in any channel
    sql = """SELECT player_id, num_wins from tic_tac_win ORDER BY num_wins DESC"""
    slack_msg = "===CURRENT TIC TAC TOE SCOREBOARD===\n"
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()

        print(f"Getting win count")

        row = cur.fetchone()

        while row is not None:
            target_str = f"*PLAYER:* <@{row[0]}>"
            numvotes_str = f"| *WINS:* {row[1]}"
            slack_msg += target_str.ljust(30) + numvotes_str.rjust(14) + "\n"
            row = cur.fetchone()

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()
    respond(slack_msg)


def convert_move_str_to_enum(move_str):
    if move_str == "OPEN":
        return TicTacMove.OPEN
    elif move_str == "X":
        return TicTacMove.X
    elif move_str == "O":
        return TicTacMove.O
    else:
        print(
            f"ERROR: move_str was none of the permitted types - it was instead {move_str}"
        )


def update_curr_move_team(team_letter_str):
    conn = None
    sql = """UPDATE tic_tac_curr_team
                SET letter = %s;"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(sql, [team_letter_str])
        conn.commit()

        print(f"Updating curr team to be {team_letter_str}")

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


# looks up whether the current turn is for O or X
# then sets the other team to be the team for the next turn
def get_and_update_curr_move_team():
    conn = None
    curr_team_str = None
    try:
        """look up whether it is a turn for team X or team O"""
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM tic_tac_curr_team;")

        print("Getting team for current move")

        row = cur.fetchone()

        while row is not None:
            curr_team_str = row[0]
            row = cur.fetchone()

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

        if curr_team_str == "X":
            print(f"Current team is {curr_team_str}")
            update_curr_move_team("O")
            return TicTacMove.X
        elif curr_team_str == "O":
            print(f"Current team is {curr_team_str}")
            update_curr_move_team("X")
            return TicTacMove.O
        else:
            print("ERROR: constructed move type was neither X nor O")


# returns (whether_game_won, winner)
# winner is arbitrary if whether_game_won is False
def whether_triple(board_state, start_index, offset):
    if (
        (board_state[start_index] != TicTacMove.OPEN)
        and (board_state[start_index] == board_state[start_index + offset])
        and (board_state[start_index] == board_state[start_index + 2 * offset])
    ):
        return True, board_state[start_index]
    else:
        for tile in board_state:
            if tile == TicTacMove.OPEN:
                return False, TicTacMove.OPEN
        # in this case, there's no winner, and the board is full
        return TIE_STR, TicTacMove.OPEN


# lst_of_checked_triples is a list of the form (whether_game_won, winner)
# in tic tac toe, it is NOT possible for more than one player to be a winner at the same time
def get_winner(lst_of_checked_triples):
    for result in lst_of_checked_triples:
        # check if there are any wins
        if result[0] == True:
            return result
    for result in lst_of_checked_triples:
        # now check if there is a tie (only valid when there is no win)
        if result[0] == TIE_STR:
            return result
    return False, TicTacMove.OPEN


def check_for_vert_win(board_state):
    offset = 3
    # vert win states start from tiles 0, 1, 2
    lst_to_check = [whether_triple(board_state, i, offset) for i in range(3)]
    return get_winner(lst_to_check)


def check_for_horiz_win(board_state):
    offset = 1
    # horiz win states start from tiles 0, 3, 6
    lst_to_check = [whether_triple(board_state, i, offset) for i in [0, 3, 6]]
    return get_winner(lst_to_check)


def check_for_diag_win(board_state):
    return get_winner(
        [whether_triple(board_state, 0, 4), whether_triple(board_state, 2, 2)]
    )


def check_for_win(board_state):
    return get_winner(
        [
            check_for_vert_win(board_state),
            check_for_horiz_win(board_state),
            check_for_diag_win(board_state),
        ]
    )


def record_win(player):
    conn = None
    try:
        """record 1 additional tic tac toe win for player"""
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        sql = """INSERT INTO tic_tac_win(player_id, num_wins)
             VALUES(%s, %s)
             ON CONFLICT (player_id)
             DO UPDATE
                SET num_wins = tic_tac_win.num_wins + 1;"""
        cur.execute(sql, [player, 1])

        # commit the changes to the database
        conn.commit()

        print(f"Recording a win for {player}")

        row = cur.fetchone()

        while row is not None:
            curr_team_str = row[0]
            row = cur.fetchone()

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


def update_board_state(row_num, col_num, curr_team):
    conn = None
    try:
        """record new state induced by current move"""
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        sql = """INSERT INTO tic_tac_board(tile_state, square_id)
             VALUES(%s, %s)
             ON CONFLICT (square_id)
             DO UPDATE
                SET tile_state = excluded.tile_state;"""
        cur.execute(
            sql, [convert_move_enum_to_str(curr_team), row_num * BOARD_WIDTH + col_num]
        )

        # commit the changes to the database
        conn.commit()

        print(
            f"Updating board state at row {row_num} and col {col_num} to be {curr_team}"
        )

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


def convert_move_enum_to_str(tile):
    if tile == TicTacMove.OPEN:
        return "_"
    elif tile == TicTacMove.X:
        return "X"
    elif tile == TicTacMove.O:
        return "O"
    else:
        print(
            "ERROR: When constructing board string, a tile was neither X nor O nor OPEN"
        )


def get_board_str(board_state):
    board_str = ""
    for i in range(BOARD_HEIGHT):
        curr_row_str = "`"
        for j in range(BOARD_WIDTH):
            curr_row_str += convert_move_enum_to_str(board_state[j + BOARD_WIDTH * i])
            curr_row_str += "|"
        # replace last-column | with `\n
        curr_row_str = curr_row_str[:-1]
        curr_row_str += "`\n"
        board_str += curr_row_str
    return board_str


def reset_board_state():
    print("Reached beginning of func reset_board_state()")
    conn = None
    values_str = "(%s, %s)," * BOARD_WIDTH * BOARD_HEIGHT
    # remove final comma
    values_str = values_str[:-1]
    sql = (
        """INSERT INTO tic_tac_board(square_id, tile_state)
             VALUES """
        + values_str
        + """ ON CONFLICT (square_id)
             DO UPDATE
                SET tile_state = excluded.tile_state;"""
    )
    rows_to_insert = [(i, "OPEN") for i in range(BOARD_HEIGHT * BOARD_WIDTH)]
    values_to_insert = []
    for i in rows_to_insert:
        values_to_insert.append(i[0])
        values_to_insert.append(i[1])
    print("rows_to_insert has len", len(rows_to_insert))
    print("rows to insert is", rows_to_insert)
    print("values to insert is", values_to_insert)
    print("sql str is", sql)
    try:
        """set all board tiles to state OPEN"""
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(sql, values_to_insert)

        # commit the changes to the database
        conn.commit()

        print("Resetting board state for a new game")

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()


def make_tic_tac_toe_move(player, row_num, col_num, respond):
    slack_msg = f"====CURRENT BOARD===\n"
    last_move_by_str = f"Last move made by <@{player}>\n"
    board_state = []
    board_index = row_num * BOARD_WIDTH + col_num
    conn = None
    try:
        """query data from the tic tac toe table"""
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"SELECT tile_state FROM tic_tac_board ORDER BY square_id ASC")

        print("Getting existing tic tac toe board")

        r = cur.fetchone()

        while r is not None:
            board_state.append(convert_move_str_to_enum(r[0]))
            r = cur.fetchone()

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

        if len(board_state) != BOARD_HEIGHT * BOARD_WIDTH:
            print("ERROR: board_state was not the correct length")
        else:

            if board_state[board_index] != TicTacMove.OPEN:
                respond("Try again - that space is already taken.")
            else:
                curr_team = get_and_update_curr_move_team()
                board_state[board_index] = curr_team

                # get next team to use in Slack msg response
                next_team = TicTacMove.get_opposite(curr_team)
                next_team_str = f"Next move will be for team `{convert_move_enum_to_str(next_team)}`\n"

                # winner currently not used because X and O team assignments don't matter
                whether_won, winner = check_for_win(board_state)
                if whether_won == True:
                    # record a win for the current player
                    record_win(player)
                    # reset the (database) board state
                    reset_board_state()
                    # print a blank board to the chat
                    slack_msg += (
                        f"This is a new game - <@{player}> won the previous game.\n"
                    )
                    slack_msg += next_team_str
                    slack_msg += BLANK_BOARD_STR
                    respond(slack_msg, response_type="in_channel")
                elif whether_won == TIE_STR:
                    # I know using a string as an third boolean is very
                    # silly - I'm sorry

                    # reset the (database) board state
                    reset_board_state()

                    slack_msg += f"The previous game ended in a tie - nobody won.\n"
                    slack_msg += last_move_by_str
                    slack_msg += next_team_str
                    slack_msg += BLANK_BOARD_STR
                    respond(slack_msg, response_type="in_channel")
                else:
                    slack_msg += last_move_by_str
                    slack_msg += next_team_str
                    # add a tile and print out the new board
                    update_board_state(row_num, col_num, curr_team)
                    board_str = get_board_str(board_state)
                    slack_msg += board_str
                    respond(slack_msg, response_type="in_channel")


# Start your app
if __name__ == "__main__":
    # test_database_connection()
    app.start(port=int(os.environ.get("PORT", 3000)))
    print("started up the Bolt server")
