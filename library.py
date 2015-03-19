import requests
import ConfigParser
import sqlite3
import sys

def make_config_dict(cp):
    '''
    Return a nested dict of sections/options by iterating through a ConfigParser instance.
    '''
    d = {}
    for s in cp.sections():
        e = {}
        for o in cp.options(s):
            e[o] = cp.get(s,o)
        d[s] = e
    return d

def make_isbndb_api_str(api_url_base, ver, fmt, api_key, endpoint, isbn_or_upc):
    s = "/"
    seq = (api_url_base, ver, fmt, api_key, endpoint, isbn_or_upc)
    return s.join(seq)

def make_library_tables(c):
    '''
    Used once to create the empty tables.
    '''
    c.execute('''CREATE TABLE library (author_id TEXT,
                                        author_name TEXT,
                                        awards_text TEXT,
                                        book_id TEXT,
                                        dewey_decimal TEXT,
                                        dewey_normal TEXT,
                                        edition_info TEXT,
                                        lib_id INTEGER PRIMARY KEY,
                                        isbn10 TEXT,
                                        isbn13 TEXT,
                                        language TEXT,
                                        lcc_number TEXT,
                                        marc_enc_level TEXT,
                                        notes TEXT,
                                        physical_description_text TEXT,
                                        publisher_id TEXT,
                                        publisher_name TEXT,
                                        publisher_text TEXT,
                                        summary TEXT,
                                        title TEXT,
                                        title_latin TEXT,
                                        title_long TEXT,
                                        urls_text TEXT                                      
                                        )''')
    c.execute('''CREATE TABLE subjects (subj_id INTEGER PRIMARY KEY,
                                        subj_lib_id INTEGER,
                                        subject TEXT,
                                        FOREIGN KEY(subj_lib_id) REFERENCES library(lib_id)
                                        )''')

def get_book(c, isbn10 = None, isbn13 = None):
    '''
    Return book data from the db; if book not found, return false.
    Takes a cursor and a two additional arguments, isbn10 and isbn13, either one of which may be None
    '''
    if isbn10 is None and isbn13 is None:
        return False
    # In case we pass in a 13 when we meant a 10, or vice versa
    elif isbn13 is None:
        isbn13 = isbn10
    elif isbn10 is None:
        isbn10 = isbn13
    r = c.execute('''SELECT * FROM library WHERE isbn10==? OR isbn13==?''', (isbn10, isbn13))
    book = r.fetchone()        
    if book is None:
        return False
    else:
        return book

def insert_book(c, book):
#    try:
    c.execute('INSERT INTO library (isbn10, isbn13) VALUES (?, ?)', (book["isbn10"], book["isbn13"]))
#        except sqlite3.IntegrityError as e:
#            pass
    pk = c.lastrowid
    # define keys that can be insertd without special handling
    ks = list(set(book.keys()) - set(("isbn10", "isbn13", "author_data", "subject_ids")))

    for k in ks:
        # Now update the new record with the remaining values
        c.execute('UPDATE library SET ' + k + '=? WHERE ROWID=?', (book[k], pk))
#            except sqlite3.InterfaceError as e:
#                pass
#            except sqlite3.OperationalError as e:
#                pass
    author_id = book["author_data"][0]["id"]
    author_name = book["author_data"][0]["name"]
    c.execute('UPDATE library SET author_id=? WHERE ROWID=?', (author_id, pk))
    c.execute('UPDATE library SET author_name=? WHERE ROWID=?', (author_name, pk))
    while book["subject_ids"]:
        c.execute('INSERT INTO subjects (subj_lib_id, subject) VALUES (?, ?)', (pk, book["subject_ids"].pop()))
    return pk

def main():
    if len(sys.argv) < 2:
        print "Usage: python " + sys.argv[0] + " <ISBN-10, ISBN-13, or UPC> (TRUE to initialize DB)"
        sys.exit()
        
    isbn = sys.argv[1]
    try:
        if sys.argv[2] == "TRUE":
            initialize_db = True
    except IndexError:
        initialize_db = False
    
    config_file = "library.conf"
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    myconfig = make_config_dict(config)
    
#    working_directory = myconfig['general']['working_directory']
    api_key = myconfig['secrets']['api_key']
    db_file = myconfig['general']['db_file']
    api_url_base = myconfig['general']['api_url_base']

    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    if initialize_db:
        make_library_tables(c)
        conn.commit()
        print "Successfully initialized database."

    if not get_book(c, isbn):
        url = make_isbndb_api_str(api_url_base, "v2", "json", api_key, "book", isbn)
        payload = {'opt': 'keystats'}
        r = requests.get(url, params=payload)
        
        if "error" in r.json().keys():
            print r.json()["error"]
            conn.close()
            sys.exit()
        else:
            book = r.json()["data"][0]
            print "Found " + isbn + " as '" + book["title"] + "'"
            insert_book(c, book)
            conn.commit()
            print "Successfully inserted " + isbn + "."
    else:
        print isbn + " already in database, refusing to insert"

    conn.close()

if __name__ == "__main__":
    main()