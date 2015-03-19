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

config_file = "library.conf"
config = ConfigParser.ConfigParser()
config.read(config_file)
myconfig = make_config_dict(config)   
#    working_directory = myconfig['general']['working_directory']
api_key = myconfig['secrets']['api_key']
db_file = myconfig['general']['db_file']
api_url_base = myconfig['general']['api_url_base']

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
    c.execute('''CREATE TABLE prices (price_id INTEGER PRIMARY KEY,
                                        price_lib_id INTEGER,
                                        currency_code TEXT,
                                        in_stock INTEGER,
                                        is_historic INTEGER,
                                        is_new INTEGER,
                                        price REAL,
                                        price_time_unix INTEGER,
                                        store_id TEXT,
                                        store_title TEXT,
                                        store_url TEXT,
                                        FOREIGN KEY(price_lib_id) REFERENCES library(lib_id)
                                        )''')

def parse_isbn(isbn):
    if len(isbn)==10:
        isbn_type = "isbn10"
    elif len(isbn)==13:
        isbn_type = "isbn13"
    else:
        isbn_type = "invalid"
    return {"isbn_type": isbn_type, "isbn":isbn}

def get_book(c, isbn):
    '''
    Return book data from the db; if book not found, return false.
    '''
    r = c.execute('''SELECT * FROM library WHERE ''' + isbn["isbn_type"] + '''=?''', (isbn["isbn"],))
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
        
    # Now get price info and insert it too
    # I am not sure if ISBNDB automatically converts 10 to 13 when necessary...
    url = make_isbndb_api_str(api_url_base, "v2", "json", api_key, "prices", book["isbn13"])
    r = requests.get(url, params={'opt': 'keystats'})
    if "error" in r.json().keys():
        pass
    else:
        prices = r.json()["data"]
        for p in prices:
            price_tuple = (pk, p["currency_code"], p["in_stock"], p["is_historic"], p["is_new"], p["price"], p["price_time_unix"], p["store_id"], p["store_title"], p["store_url"])
            c.execute('INSERT INTO prices (price_lib_id, currency_code, in_stock, is_historic, is_new, price, price_time_unix, store_id, store_title, store_url) VALUES (?,?,?,?,?,?,?,?,?,?)', price_tuple)
    return pk

def make_library_db(db_file):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    make_library_tables(c)
    conn.commit()
    return conn

def delete_book(c, isbn):
    (pk, ) = c.execute('SELECT lib_id FROM library WHERE ' + isbn["isbn_type"] + '=?', (isbn["isbn"],)).fetchone()
    c.execute('DELETE FROM subjects WHERE subj_lib_id=?', (pk,))
    c.execute('DELETE FROM prices WHERE price_lib_id=?', (pk,))
    c.execute('DELETE FROM library WHERE lib_id=?', (pk,))

def main():
    try:
        if sys.argv[1] == "TRUE":
            conn = make_library_db(db_file)
            print "Successfully initialized database."
    except IndexError:
        conn = sqlite3.connect(db_file)
    finally:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
    
    try:
        while True:
            isbn = raw_input("Scan barcode or enter ISBN: ")
            isbn = parse_isbn(isbn)
            if isbn["isbn_type"] == "invalid":
                print "Invalid ISBN!"
                continue
            elif not get_book(c, isbn):
                url = make_isbndb_api_str(api_url_base, "v2", "json", api_key, "book", isbn["isbn"])
                r = requests.get(url, params={'opt': 'keystats'})
                
                if "error" in r.json().keys():
                    print r.json()["error"]
                else:
                    book = r.json()["data"][0]
                    print "Found " + isbn["isbn"] + " as '" + book["title"] + "'"
                    insert_book(c, book)
                    conn.commit()
                    print "Successfully inserted " + isbn["isbn"] + " (" + book["title"] + ")."
            else:
                book = get_book(c, isbn)
                isbn2 = raw_input(isbn["isbn"] + " (" + book["title"] + ") already in database. To delete, scan or enter ISBN again: ")
                if isbn["isbn"]==isbn2:
                    delete_book(c, isbn)
                    conn.commit()
                    print "Deleted " + isbn["isbn"] + " (" + book["title"] + ")."
                else:
                    print "ISBNs did not match!"
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()

if __name__ == "__main__":
    main()