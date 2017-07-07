#!/usr/bin/env python
# coding: utf-8
"""
file: 'parse.py'
description:
    This python script can take high-level requests to fetch and parse
    rawacf data from SuperDARN via Globus and using the 'backscatter' 
    library. 

    The methods contained herein can also be used externally to 
    perform these high-level processing functions.

author: David Fairbairn
date: July 6 2017
"""

import logging
import os

from datetime import datetime as dt
import numpy as np
import sqlite3
import argparse

import backscatter 
import rawacf_utils as rut
from rawacf_utils import two_pad

BAD_RAWACFS_FILE = './bad_rawacfs.txt'
BAD_CPIDS_FILE = './bad_cpids.txt'
LOG_FILE = 'parse.log'

logging.basicConfig(level=logging.DEBUG,
    format='%(levelname)s %(asctime)s: %(message)s', 
    datefmt='%m/%d/%Y %I:%M:%S %p')

logFormatter = logging.Formatter('%(levelname)s %(asctime)s: %(message)s')
rootLogger = logging.getLogger()

fileHandler = logging.FileHandler("./{0}".format(LOG_FILE))
fileHandler.setFormatter(logFormatter)
rootLogger.addHandler(fileHandler)

# -----------------------------------------------------------------------------
#                           High-Level Methods 
# -----------------------------------------------------------------------------

def process_rawacfs_day(year, month, day, station_code=None, conn=None):
    """
    A function which fetches and processes rawacfs from a particular day
    into the sqlite3 database. Can optionally select a particular day.

    :param year:
    :param month:
    :param day: 
    [:param station_code:] 3-letter [string] for the station e.g. 'sas' for Saskatoon

    ** Note: it would've been ideal to take station ID parameters but I didn't
            know of a really quick and easy way to convert stid's and station codes
            without requiring an installation of e.g. davitpy **
    """
    import subprocess
    import calendar 

    if conn==None:
        conn = sqlite3.connect("superdarntimes.sqlite")

    # If a stid is given to function, then just grab that station's stuff
    all_stids = True if station_code is None else False

    # I. Run the globus connect process
    rut.globus_connect()

    # II. Fetch the files
    if all_stids:
        script_query = [rut.SYNC_SCRIPT_LOC,'-y', str(year), '-m',
            str(month), '-p', str(year)+two_pad(month)+two_pad(day)+"*", rut.ENDPOINT]
    else:
        # The case that we're looking at just one particular station
        script_query = [rut.SYNC_SCRIPT_LOC,'-y', str(year), '-m',
            str(month), '-p', str(year)+two_pad(month)+two_pad(day)+"*"+station_code, 
            rut.ENDPOINT]
    rut.globus_query(script_query)

    # III.
    # B. Parse the rawacf files, save their metadata in our DB
    parse_rawacf_folder(rut.ENDPOINT, conn=conn)
    logging.info("\t\tDone with parsing {0}-{1}-{2} rawacf data".format(
                 str(year), two_pad(month), two_pad(day)))
    conn.commit()

    # C. Clear the rawacf files that were fetched in this cycle
    try:
        rut.clear_endpoint()
        logging.info("\t\tDone with clearing {0}-{1}-{2} rawacf data".format(
                 str(year), two_pad(month), two_pad(day)))
    except subprocess.CalledProcessError:
        logging.error("\t\tUnable to remove files.")
    logging.info("Completed processing of requested day's rawacf data.")
 
def process_rawacfs_month(year, month, conn=sqlite3.connect("superdarntimes.sqlite")):
    """
    Takes starting month and year and ending month and year as arguments. Steps
    through each day in each year/month combo

    :param year: [int] indicating the year to look at
    :param month: [int] indicating the month to look at
    :param conn: [sqlite3 connection] to the database for saving to

    ** On Maxwell this has taken upwards of 14 hours to run for a given month **

    """
    import subprocess
    import calendar 

    # I. Run the globus connect process
    rut.globus_connect()

    logging.info("Beginning to process Rawacf logs... ")
    
    last_day = calendar.monthrange(year, month)[1]
    logging.info("Starting to analyze {0}-{1} files...".format(str(year), two_pad(month))) 

    # II. For each day in the month:
    for day in np.arange(1,last_day+1):

        logging.info("\tLooking at {0}-{1}-{2}".format(
                     str(year), two_pad(month), two_pad(day)))

        # A. First, grab the rawacfs via globus (and wait on it)
        script_query = [rut.SYNC_SCRIPT_LOC,'-y', str(year), '-m',
            str(month), '-p', str(year)+two_pad(month)+two_pad(day)+"*", rut.ENDPOINT]

        rut.globus_query(script_query)

        # B. Parse the rawacf files, save their metadata in our DB
        parse_rawacf_folder(rut.ENDPOINT, conn=conn)
        logging.info("\t\tDone with parsing {0}-{1}-{2} rawacf data".format(
                     str(year), two_pad(month), two_pad(day)))

        # C. Clear the rawacf files that were fetched in this cycle
        try:
            rut.clear_endpoint()
            logging.info("\t\tDone with clearing {0}-{1}-{2} rawacf data".format(
                     str(year), two_pad(month), two_pad(day)))
        except subprocess.CalledProcessError:
            logging.error("\t\tUnable to remove files.")

    logging.info("Completed processing of requested month's rawacf data.")
    return
        
def test_process_rawacfs(conn=sqlite3.connect("superdarntimes.sqlite")):
    """
    This method exists specifically to test whether everything's 
    configured properly to run the script to grab an entire month's data. 
    It does everything that process_rawacfs_month does, but only a little bit.

    :param conn: [sqlite3 connection] to the database
    """
    import subprocess

    # Test 1: Globus query
    rut.globus_connect()
    script_query = [rut.SYNC_SCRIPT_LOC,'-y', '2017', '-m',
        '02', '-p', '20170209.0*sas', rut.ENDPOINT]
    rut.globus_query(script_query)

    # Test 2: verify that we can parse this stuff
    parse_rawacf_folder(rut.ENDPOINT, conn=conn )
    logging.info("Done with parsing 2017-02-09 'sas' rawacf data")

    # Test 3: Clear the rawacf files that we fetched
    try:
        rut.clear_endpoint()
        logging.info("Successfully removed 2017-02-09 'sas' rawacf data")

    except subprocess.CalledProcessError:
        logging.error("\t\tUnable to remove files")
 
def parse_rawacf_folder(folder, conn=sqlite3.connect("superdarntimes.sqlite")):
    """
    Takes a path to a folder which contains of .rawacf files, parses them
    and inserts them into the database.

    :param folder: [str] indicating the path and name of a folder to read 
                    rawacf files from
    :param conn: [sqlite3 connection] to the database
    """
    import multiprocessing as mp
    assert(os.path.isdir(folder))
    cur = conn.cursor()
    logging.info("Acceptable path {0}. Analysis proceeding...".format(folder))

    #pool = mp.Pool()
    #pool.map(parse_file, os.listdir(folder)) # missing folder and index args 

    processes = []
    for i, fil in enumerate(os.listdir(folder)):
        p = mp.Process(target=parse_file, args=(folder, fil, i,))
        p.start()
        processes.append(p)
        #parse_file(folder, fil, index=i)

    for p in processes:
        p.join()

    # Commit the database changes
    conn.commit()

def parse_file(path, fname, index=1):
    """
    Takes an individual .rawacf file, tries opening it, tries using 
    backscatter to parse it, and tries processing the data in to the 
    sqlite database.

    :param path: [string] path to file
    :param fname: [string] name of rawacf file
    [:param index:] [int] number of file in directory. Helpful for logging.
    """
    logging.info("{0} File: {1}".format(index, fname)) 
    try:
        if fname[-4:] == '.bz2':
            dics = rut.bz2_dic(path + '/' + fname)
        elif fil[-7:] == '.rawacf':
            dics = rut.acf_dic(path + '/' + fname)
        else:
            logging.info('\t{0} File {1} not used for dmap records.'.format(index, fname))
            return
    except backscatter.dmap.DmapDataError as e:
        err_str = "\t{0} File: {1}: Error reading dmap from stream - possible record" + \
                  " corruption. Skipping file."
        logging.error(err_str.format(index, fname))
        #logging.exception(e)

        # ***ADD TO LIST OF BAD_RAWACFS ***
        with open(BAD_RAWACFS_FILE, 'a') as f:
            # Backscatter exceptions have an awkward newline that looks bad in 
            # logs, so I remove them here
            e_tmp = str(e).split('\n')
            e_tmp = reduce(lambda x, y: x+y, e_tmp)
            f.write(fname + ':"' + str(e_tmp) + '"\n')
        return
     
    # If it was a bz2 or rawacf, now we do scripty stuff with dict
    try:
        r = rut.process_experiment(dics, conn)
        conn.commit()
        if r.not_corrupt == False:
            err_str = 'Data inconsistency encountered in rawacf file.'.format(index, fname)
            raise rut.BadRawacfDataError(err_str)
        # Else, log the successful processing
        logging.info('\t{0} File  {1}: File processed.'.format(index, fname))
    except Exception as e:
        err_str = "\t{0} File {1}: Exception raised during process_experiment: {2}"
        logging.warning(err_str.format(index, fname, e))
        #logging.exception(e)
        # ***ADD TO LIST OF BAD_CPIDS ***
        with open(BAD_CPIDS_FILE, 'a') as f:
            f.write(fname + ':' + str(e) + '\n')

#------------------------------------------------------------------------------ 
#                       Command-Line Usability
#------------------------------------------------------------------------------ 

def get_args():
    """
    Parse the command-line arguments.

    Yes, in an ideal world, this whole thing would be a sweet little 
    object which does things on initialization, but at least for now,
    this works as a stand-alone function!
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-y", "--rec_year", help="Year you wish to process records for",
                        type=int)
    parser.add_argument("-m", "--rec_month", help="Month you wish to process records for",
                        type=int)
    parser.add_argument("-d", "--rec_day", help="Day you wish to process records for",
                        type=int)
    parser.add_argument("-p", "--directory", help="Indicate a directory to parse rawacfs in")

    parser.add_argument("-f", "--fname", help="Indicate a filename to process")

    # For now, we require a particular station to be requested
    parser.add_argument("-c", "--station_code", 
                        help="SuperDARN Station Code you want stats for (e.g. 'sas')")

    parser.add_argument("-q", "--quiet", help="Use quiet mode",
                        action="store_true")
    args = parser.parse_args()
    return args

def process_args(year, month, day, st_code, directory, fname):
    """
    Function which handles interpreting what kind of processing request
    to make.
    """
    # Highest precedence: if a particular file is provided as an arg.
    if fname is not None:
        if os.path.isfile(fname):
            logging.info("Parsing file {0}".format(fname))
            #parse_file(os.path.dirname(fname), os.path.basename(fname))
            return
        else:
            logging.error("Invalid filename.")

    # Next level of precedence: if a directory is supplied
    if directory is not None:
        if os.path.isdir(directory): 
            logging.info("Parsing files in directory {0}".format(directory))
            #parse_rawacf_folder(directory)
            return
        else:
            logging.error("Invalid directory.")

    if year is not None and month is not None:
        # Next check if a day was provided
        if day is not None:
            msg = "Proceeding to fetch and parse data from {0}-{1}-{2}"
            logging.info(msg.format(year, month, day))
            logging.info("By the way, station code supplied to this was: '{0}'".format(st_code))
            #process_rawacfs_day(year, month, day, station_code=st_code)
            return
        else:
            msg = "Proceeding to fetch and parse data in {0}-{1}"
            logging.info(msg.format(year, month))
            #process_rawacfs_month(year, month)
            return
    else:
        logging.info("Some form of argument is kinda required!")

def initialize_logger(quiet_mode):
    """
    Function for setting up the initial logging parameters

    :param use_verbose: [boolean] flag indicating whether to be verbose.
        ** If _not_ running parse/fetch requests from the command-line **
    """
    level = logging.WARNING if quiet_mode else logging.DEBUG

    logging.basicConfig(level=level,
        format='%(levelname)s %(asctime)s: %(message)s', 
        datefmt='%m/%d/%Y %I:%M:%S %p')
 
    logFormatter = logging.Formatter('%(levelname)s %(asctime)s: %(message)s')
    rootLogger = logging.getLogger()
    rootLogger.setLevel(level)

    fileHandler = logging.FileHandler("./{0}".format(LOG_FILE))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

#------------------------------------------------------------------------------ 

if __name__ == "__main__":
    args = get_args()

    year = args.rec_year
    month = args.rec_month
    day = args.rec_day
    st_code = args.station_code
    directory = args.directory
    fname = args.fname
    quietness_mode = args.quiet
    
    initialize_logger(quietness_mode)

    rut.read_config() 
    conn = rut.connect_db()
    cur = conn.cursor()
    process_args(year, month, day, st_code, directory, fname)
    