# todo: add a way to refresh price info from the API

import requests
import ConfigParser
import sqlite3
import serial
import HTML
import threading
import Queue
import time

def serial_input(q, ser):
    while True:
        try:
            isbn = ser.readline().strip()
            q.put(isbn)
        except serial.SerialException:
            continue

def keyboard_input(q):
    while True:
        isbn = raw_input()
        q.put(isbn)

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
    def __keys__(self):
        return self.__dict__.keys()

class Catalog(object):
    def __init__(self, library):
        self.list = library.catalog()
        self.library = library
    def __len__(self):
        return len(self.list)
    def __repr__(self):
        return repr(self.list)
    def __nonzero__(self):
        return True
    def write(self, catalog_file):
        self.catalog_file = catalog_file
        f = open(self.catalog_file, 'w')
        mytable = HTML.Table(header_row=["Author", "Title", "Publisher", "ISBN", "Sells For", "Yours For"],
                            col_align=["left", "left", "left", "left", "right", "right"],
                            col_styles=["", "font-style: italic", "", "font-size: small", "", "font-weight: bold"])
        for book in self.list:
            min_price = self.library.min_price(book)
            if min_price:
                sells_for = self.library.min_price(book) + 2
                yours_for = int(sells_for * 0.75)
                sells_for = "$" + "%.2f" % sells_for
                yours_for = "$" + "%.2f" % yours_for
            else:
                sells_for = "-"
                yours_for = "e-mail for price"
            # HTML module can't hande Unicode
            ascii_strings = []
            for s in [book.author_name, book.title, book.publisher_name]:
                ascii_strings.append(s.encode('ascii', errors="replace"))
            mytable.rows.append([ascii_strings[0], ascii_strings[1], ascii_strings[2], book.isbn13, sells_for, yours_for])
        mytable.rows.sort()
        html = str(mytable)
        f.write(html)
        f.close()

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
    def make_isbndb_api_req(self, ver, fmt, endpoint, search_term, search_index=None):
        '''
        Construct and sends an API request to ISBN DB. Return the request.
        '''
        s = "/"
        p = {'opt': 'keystats'}
        if endpoint == "books":
            seq = (self.api_url_base, ver, fmt, self.api_key, endpoint)
            p['q'] = search_term
            if search_index:
                p['i'] = search_index
        else:
            seq = (self.api_url_base, ver, fmt, self.api_key, endpoint, search_term)
        url = s.join(seq)
        r = requests.get(url, params=p)
        return r        
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
            r = self.make_isbndb_api_req("v2", "json", "prices", book.isbn13)
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
    def search(self, search_term):
        '''
        Needs to be rewritten to handle all possible search queries
        '''
        isbn = self.fmt_isbn(search_term)
        if isbn["isbn_type"] != "invalid":
            r = self.c.execute('''SELECT * FROM library WHERE ''' + isbn["isbn_type"] + '''=?''', (isbn["isbn"],))
        elif search_term.isdigit():
            # Here we assume that it is simply an invalid ISBN
            return False
        else:
            # Any other input is treated as a potential title
            r = self.c.execute('''SELECT * FROM library WHERE title LIKE ?''', ('%' + search_term + '%',))

        book_data = r.fetchall()
        if not book_data:
            return False
        else:
            books = []
            for b in book_data:
                book = Book(b)
                books.append(book)
                print "Found " + book.title + " (" + book.isbn13 + ") in library."
            if len(books) == 1:
                return books[0]
            else:
                # This will break other things that don't expect a list...
                return books
    def api_search(self, search_term):
        '''
        Search ISBNDB for an ISBN
        '''
        isbn = self.fmt_isbn(search_term)
        if isbn["isbn_type"] != "invalid":
            r = self.make_isbndb_api_req("v2", "json", "book", isbn["isbn"])
        elif search_term.isdigit():
            # Here we assume that it is simply an invalid ISBN
            return False
        else:
            # Any other input is treated as a potential title
            r = self.make_isbndb_api_req("v2", "json", "books", search_term)      
        
        if "error" in r.json().keys():
            print r.json()["error"]
            return False
        elif len(r.json()['data']) > 1:
            print "Found multiple matching titles online (currently unsupported)."
            return False
        else:
            book_data = r.json()["data"][0]
            book = Book(book_data)
            print "Found " + book.title + " (" + book.title + ") online."
            return book      
    def catalog(self):
        '''
        Returns a catalog (list of all books in the library) of Books
        '''
        rs = self.c.execute('''SELECT isbn13 FROM library''').fetchall()
        catalog = []
        for r in rs:
            (isbn, ) = r
            book = self.search(isbn)
            catalog.append(book)
        return catalog
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
    #import os
    #os.chdir("/Users/gjm/bin/library")
    config_file = "library.conf"
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    myconfig = make_config_dict(config)   
    
    api_key = myconfig['secrets']['api_key']
    db_file = myconfig['general']['db_file']
    api_url_base = myconfig['general']['api_url_base']
    serial_port = myconfig['general']['serial_port']
    serial_speed = int(myconfig['general']['serial_speed'])
    
    q = Queue.Queue()
    
    try:
        ser = serial.Serial(serial_port, serial_speed)
    except OSError:
        ser = None
        print "Error opening serial port. Is the barcode scanner plugged in?"

    mylibrary = Library(db_file, api_key, api_url_base)

    if ser:
        serial_thread = threading.Thread(target=serial_input, args=(q, ser))
        serial_thread.daemon = True
        serial_thread.start()
    
    print "\nScan barcode or enter ISBN."
            
    keyboard_thread = threading.Thread(target=keyboard_input, args=(q,))
    keyboard_thread.daemon = True
    keyboard_thread.start()

    try:
        while True:
            if q.empty():
                time.sleep(0.005)                
            else:
                isbn = q.get()
                if isbn == "catalog":
                    Catalog(mylibrary).write("catalog.html")
                elif isbn == "quit":
                    raise KeyboardInterrupt
                else:
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
                print "\nScan barcode or enter ISBN."
    except KeyboardInterrupt:
        pass
    finally:
        if ser:
            ser.close()
        mylibrary.close()

if __name__ == "__main__":
    main()