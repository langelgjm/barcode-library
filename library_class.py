import requests
import ConfigParser
import sqlite3
import serial

class Book(object):
    '''
    Books are created either from the JSON resulting from an API query, or from the results of an SQL query.
    '''
    def __init__(self, book_data):
        # exclude special keys (i.e., those that contain lists); note the important comma in the second set
        ks = list(set(book_data.keys()) - set(("author_data", )))
        for k in ks:
            self.__setattr__(k, book_data[k])
        # When dealing with JSON
        if "author_data" in book_data.keys():
            self.author_id = book_data["author_data"][0]["id"]
            self.author_name = book_data["author_data"][0]["name"]
            # Don't forget to remove the author_data key
            # Note that we pop off author_data HERE because trying to pop it off an sqlite3.Row probably won't work
            book_data.pop("author_data", None)
    def __len__(self):
        return len(self.__dict__)
    def __repr__(self):
        return repr(self.__dict__)
    def __nonzero__(self):
        return True

class Library(object):
    def __init__(self, db_file, api_key, api_url_base):
        self.db_file = db_file
        self.api_key = api_key
        self.api_url_base = api_url_base
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self.c = self.conn.cursor()
        # Check if we need to create tables:
        r = self.c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library'").fetchone()
        if r is None:
            self.create_tables()
    def __len__(self):
        try:
            (n, ) = self.c.execute('''SELECT COUNT(*) FROM library''').fetchone()
        except sqlite3.OperationalError:
            n = 0
        return n
    def __repr__(self):
        s = "<Library of " + str(len(self)) + " books stored in '" + self.db_file + "'>"
        return s
    def __nonzero__(self):
        return True
    def create_tables(self):
        '''
        Used once to create the empty tables.
        '''
        self.c.execute('''CREATE TABLE IF NOT EXISTS library (author_id TEXT,
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
        self.c.execute('''CREATE TABLE IF NOT EXISTS subjects (subj_id INTEGER PRIMARY KEY,
                                            subj_lib_id INTEGER,
                                            subject TEXT,
                                            FOREIGN KEY(subj_lib_id) REFERENCES library(lib_id)
                                            )''')
        self.c.execute('''CREATE TABLE IF NOT EXISTS prices (price_id INTEGER PRIMARY KEY,
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
        self.conn.commit()
    def fmt_isbn(self, isbn):
        if len(isbn)==10:
            isbn_type = "isbn10"
        elif len(isbn)==13:
            isbn_type = "isbn13"
        else:
            isbn_type = "invalid"
        return {"isbn_type": isbn_type, "isbn": isbn}
    def make_isbndb_api_str(self, ver, fmt, endpoint, isbn):
        s = "/"
        seq = (self.api_url_base, ver, fmt, self.api_key, endpoint, isbn)
        return s.join(seq)
    def insert(self, book):
        if not self.search(book.isbn13):
            self.c.execute('INSERT INTO library (isbn10, isbn13) VALUES (?, ?)', (book.isbn10, book.isbn13))
            pk = self.c.lastrowid
            # define keys that can be inserted without special handling
            ks = list(set(book.__dict__.keys()) - set(("isbn10", "isbn13", "subject_ids")))
            for k in ks:
                # Now update the new record with the remaining values
                self.c.execute('UPDATE library SET ' + k + '=? WHERE ROWID=?', (book.__dict__[k], pk))
            while book.subject_ids:
                self.c.execute('INSERT INTO subjects (subj_lib_id, subject) VALUES (?, ?)', (pk, book.subject_ids.pop()))
            # Now get price info and insert it too
            # I am not sure if ISBNDB automatically converts 10 to 13 when necessary...
            url = self.make_isbndb_api_str("v2", "json", "prices", book.isbn13)
            r = requests.get(url, params={'opt': 'keystats'})
            if "error" in r.json().keys():
                pass
            else:
                prices = r.json()["data"]
                for p in prices:
                    price_tuple = (pk, p["currency_code"], p["in_stock"], p["is_historic"], p["is_new"], p["price"], p["price_time_unix"], p["store_id"], p["store_title"], p["store_url"])
                    self.c.execute('INSERT INTO prices (price_lib_id, currency_code, in_stock, is_historic, is_new, price, price_time_unix, store_id, store_title, store_url) VALUES (?,?,?,?,?,?,?,?,?,?)', price_tuple)
            self.conn.commit()        
            print "Inserted " + book.title + " (" + book.isbn13 + ") into library."
            return pk
        else:
            print "Cannot insert " + book.title + " (" + book.isbn13 + "): already in library."
    def remove(self, book):
        '''
        FIXME
        '''
        if self.search(book.isbn13):
            (pk, ) = self.c.execute('SELECT lib_id FROM library WHERE isbn13=?', (book.isbn13,)).fetchone()
            self.c.execute('DELETE FROM subjects WHERE subj_lib_id=?', (pk,))
            self.c.execute('DELETE FROM prices WHERE price_lib_id=?', (pk,))
            self.c.execute('DELETE FROM library WHERE lib_id=?', (pk,))
            self.conn.commit()
            print "Removed " + book.title + " (" + book.isbn13 + ") from library."
        else:
            print "Cannot remove " + book.title + " (" + book.isbn13 + "): not in library."
    def search(self, isbn):
        '''
        Needs to be rewritten to handle all possible search queries and return a Book object.
        '''
        isbn = self.fmt_isbn(isbn)
        if isbn["isbn_type"] != "invalid":
            r = self.c.execute('''SELECT * FROM library WHERE ''' + isbn["isbn_type"] + '''=?''', (isbn["isbn"],))
            book_data = r.fetchone()     
            if book_data is None:
                return False
            else:
                book = Book(book_data)
                print "Found " + book.title + " (" + book.isbn13 + ") in library."
                return book
        else:
            return False
    def api_search(self, isbn):
        '''
        Needs to be rewritten to return a Book object.
        '''
        isbn = self.fmt_isbn(isbn)
        if isbn["isbn_type"] != "invalid":
            url = self.make_isbndb_api_str("v2", "json", "book", isbn["isbn"])
            r = requests.get(url, params={'opt': 'keystats'})
            if "error" in r.json().keys():
                print r.json()["error"]
                return False
            else:
                book_data = r.json()["data"][0]
                book = Book(book_data)
                print "Found " + book.title + " (" + book.title + ") online."
                return book
        else:
            return False
    def subjects(self, book):
        r = self.c.execute('''SELECT lib_id FROM library WHERE isbn13=?''', (book.isbn13,)).fetchone()
        if r:
            (subj_lib_id, ) = r
            rs = self.c.execute('''SELECT subject FROM subjects WHERE subj_lib_id=?''', (subj_lib_id,)).fetchall()
            subjects = []
            for r in rs:
                (subject, ) = r
                subjects.append(subject)
            return subjects
        else:
            print "Couldn't find " + book.title + " (" + book.isbn13 + ") in library. Perhaps you need to insert it first?"
            return False
    def min_price(self, book):
        r = self.c.execute('''SELECT lib_id FROM library WHERE isbn13=?''', (book.isbn13,)).fetchone()
        if r:
            (price_lib_id, ) = r
            r = self.c.execute('''SELECT MIN(price) FROM prices WHERE price_lib_id=?''', (price_lib_id,)).fetchone()
            if r:
                (min_price, ) = r
                return min_price
            else:
                print "Couldn't find any prices for " + book.title + " (" + book.isbn13 + ") in library."
                return False
        else:
            print "Couldn't find " + book.title + " (" + book.isbn13 + ") in library. Perhaps you need to insert it first?"
            return False
    def close(self):
        '''
        Only call when done using library.
        '''
        self.conn.close()

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

def main():
    config_file = "library.conf"
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    myconfig = make_config_dict(config)   
    
    api_key = myconfig['secrets']['api_key']
    db_file = myconfig['general']['db_file']
    api_url_base = myconfig['general']['api_url_base']
    serial_port = myconfig['general']['serial_port']
    serial_speed = int(myconfig['general']['serial_speed'])
    
    ser = serial.Serial(serial_port, serial_speed)
    mylibrary = Library(db_file, api_key, api_url_base)
    
    try:
        while True:
            print "Scan barcode or enter ISBN: "
            # We probably need to run the serial portion in a separate thread...
            #isbn = raw_input("Scan barcode or enter ISBN: ")
            isbn = ser.readline().strip()
            book = mylibrary.search(isbn)
            if not book:
                book = mylibrary.api_search(isbn)
                if book:
                    mylibrary.insert(book)
                else:
                    print "Cannot find " + isbn + " in library or online."
            else:
                print book
                print "Subjects: " + str(mylibrary.subjects(book))
                print "Minimum price: " + str(mylibrary.min_price(book))
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        mylibrary.close()

if __name__ == "__main__":
    main()