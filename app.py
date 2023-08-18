
import os
from flask import Flask, render_template, send_from_directory
import sqlite3 as sql
import math
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

IMG_DIR = os.environ['IMG_DIR'] if os.environ['IMG_DIR'] else "july-book"
# both are set in docker env
# it expects a directory of directories of images
# main_dir > topic_dir > img.svg

DATA_PATH = '/mnt/data/'
DB_PATH = DATA_PATH + 'Scores.db'
CURRENT_DATE = datetime.today().strftime('%Y-%m-%d')

def create_default_elo_record(fname, topic):
    print("Creating default record for: " + fname)
    conn = sql.connect(DB_PATH)
    conn.execute(
        "INSERT INTO elo (fname, topic, bouts, score, date_added, date_last_modified) VALUES(?, ?, 0, 1000, ?, ?)",
        (fname, topic, CURRENT_DATE, CURRENT_DATE)
    )
    conn.commit()
    conn.close()
    return 'OK'

# Elo parameters
K = 32  # The K-factor determines the impact of each game result

def calculate_expected_score(rating_a, rating_b, scale):
    """
    Calculate the expected score for a player A against player B based on their ratings.

    Args:
        rating_a (float): Rating of player A.
        rating_b (float): Rating of player B.
        scale (int): The scale indicating the preference (from -2 to 2, -2 being strongly prefer B, 2 being strongly prefer A).

    Returns:
        float: The expected score for player A.
    """
    expected_a = 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))
    
    if scale < 0:
        expected_a *= (abs(scale) + 1)
    elif scale > 0:
        expected_a /= (scale + 1)
        
    return expected_a

def calculate_updated_rating(rating_a, rating_b, scale_a):
    """
    Calculate the updated rating for a player A based on the result against player B.

    Args:
        rating_a (float): Rating of player A.
        rating_b (float): Rating of player B.
        scale_a (int): The scale indicating the preference of player A (from -2 to 2, -2 being strongly prefer B, 2 being strongly prefer A).

    Returns:
        float: The updated rating for player A.
    """
    expected_a = calculate_expected_score(rating_a, rating_b, scale_a)
    
    if scale_a < 0:
        score_a = 0
    elif scale_a > 0:
        score_a = 1
    else:
        score_a = 0.5
        
    updated_rating_a = rating_a + K * (score_a - expected_a)
    return updated_rating_a

def update_rating(img_rating, opponent_rating, outcome):
    return calculate_updated_rating(img_rating, opponent_rating, outcome)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/solo')
def solo():
    return render_template('solo.html')


@app.route('/db/create_scores_table')
def db_create_score_tbl():
    conn = sql.connect(DB_PATH)
    print("Opened database successfully")

    conn.execute('CREATE TABLE scores (fname TEXT, topic TEXT, score INTEGER)')
    print("Table created successfully")
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/db/create_elo_table')
def db_create_elo_tbl():
    conn = sql.connect(DB_PATH)
    print("Opened database successfully")

    conn.execute('CREATE TABLE elo (fname TEXT, topic TEXT, bouts INTEGER, score INTEGER)')
    conn.commit()
    print("Table created successfully")
    conn.close()
    return 'OK'

@app.route('/list')
def list():
   con = sql.connect(DB_PATH)
   con.row_factory = sql.Row
   
   cur = con.cursor()
   cur.execute("SELECT * FROM elo ORDER BY score DESC, bouts DESC")
   
   rows = cur.fetchall()
   con.close()
   return render_template("list.html",rows = rows)


#serving

@app.route('/json-data/<path:path>')
def send_report(path):
    return send_from_directory(DATA_PATH + 'json-data', path)


@app.route('/images/<path:topic>/<path:filename>')
def serve_image(topic, filename):
    return send_from_directory(DATA_PATH + IMG_DIR +'/'+topic+'/', filename)


@app.route('/images/<path:topic>/<path:filename>/action/<path:action>')
def image_action(topic, filename, action):
    new_val = 0
    if action == "like":
        new_val = 1
    elif action == "dislike":
        new_val = -1
    else:
        return 'NO CHANGE'
    con = sql.connect(DB_PATH)
    con.row_factory = sql.Row

    cur = con.cursor()
    cur.execute(f"select * from scores where topic = ? and fname = ? limit 1", (topic,filename))
    rows = cur.fetchall()
    print(rows)
    if len(rows) < 1:
    # DNE
        create_cur = con.cursor()
        create_cur.execute("INSERT INTO scores VALUES (?, ?, ?, ?, ?)",(filename,topic,new_val,CURRENT_DATE,CURRENT_DATE))
        con.commit()
        create_rows = create_cur.fetchall()
        print("Inserted")
        print(create_rows)
    else:
        # does exist
        print("Row exists? Updating...")
        print(rows[0])
        result = rows[0]

        old_score = result.score
        new_score = old_score + new_val

        update_cur = con.cursor()

        #we're assuming all records have 'date_created' so we need to check to see if we need to fix that here
        old_date_created = result.date_added
        if old_date_created:
            update_cur.execute("UPDATE scores SET score = ?, date_last_modified WHERE fname = ?, topic = ?", (new_score,CURRENT_DATE,filename,topic))
        else:
            update_cur.execute("UPDATE scores SET score = ?, date_added, date_last_modified WHERE fname = ?, topic = ?", (new_score,CURRENT_DATE,CURRENT_DATE,filename,topic))
        con.commit()
        update_rows = update_cur.fetchall()
        print("Updated")
        print(update_rows)
        conn.close()
    return 'OK'



@app.route('/image_compare/<path:topic>/img1/<path:img1_fname>/img2/<path:img2_fname>/outcome/<path:outcome>', methods = ['POST'])
def image_compare(topic, img1_fname, img2_fname, outcome):
    winner = ''
    loser = ''
    img1_winner = 0
    img2_winner = 0
    if 'a' in outcome:
        img1_winner = 1
        winner = img1_fname
        loser = img2_fname
    elif 'b' in outcome:
        img2_winner = 1
        winner = img2_fname
        loser = img1_fname
    
    outcome_factor = 0
    if 'strongly-prefer' in outcome:
        outcome_factor = 2
    elif 'prefer' in outcome:
        outcome_factor = 1

    #change elo based on this
    con = sql.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(f"select * from elo where topic = ? and (fname = ? OR fname = ?) limit 2", (topic,winner,loser))
    rows = cur.fetchall()

    #defaults for newbs
    winner_rating = 1000
    loser_rating = 1000
    winner_bouts = 0
    loser_bouts = 0

    # flags so we know if the records need inserting or updating
    img1_db_rec_exists = 0
    img2_db_rec_exists = 0

    if rows:
        #changing defaults if we have DB entries
        for each_rec in rows:
            print("each rec")
            print(each_rec)
            if each_rec[0] == winner:
                winner_rating = each_rec[3]
                winner_bouts = each_rec[2]
            elif each_rec[0] == loser:
                loser_rating = each_rec[3]
                loser_bouts = each_rec[2]

            #toggle flags if we find the records
            if each_rec[0] == img1_fname:
                img1_db_rec_exists = 1
            elif each_rec[0] == img2_fname:
                img2_db_rec_exists = 1

    # we need to insert for the records that dont exist
    if not img1_db_rec_exists:
        create_default_elo_record(fname=img1_fname, topic=topic)
    elif not img2_db_rec_exists:
        create_default_elo_record(fname=img2_fname, topic=topic)

    # calculating the new elo ratings & bout count
    new_winner_rating = update_rating(winner_rating, loser_rating, outcome_factor)
    new_loser_rating = update_rating(loser_rating, winner_rating, outcome_factor*-1)

    new_winner_bouts = winner_bouts + 1
    new_loser_bouts = loser_bouts + 1

    # updating db to reflect new values
    print("Updating both records...")
    update_cur = con.cursor()
    update_cur.execute(
        "UPDATE elo SET bouts = ?, score = ? WHERE topic = ? and fname = ?",
        (new_winner_bouts, new_winner_rating, topic, winner)
    )
    update_cur.execute(
        "UPDATE elo SET bouts = ?, score = ? WHERE topic = ? and fname = ?",
        (new_loser_bouts, new_loser_rating, topic, loser)
    )
    con.commit()
    con.close()
    return "Success", 200, {"Access-Control-Allow-Origin": "*"}
