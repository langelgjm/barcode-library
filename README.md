# barcode-library

Python and Arduino code for creating a library database with a barcode scanner.

I want to sell some of my books and catalog the rest, but I don't want to have to manually enter or look up information or prices. The Arduino code permits the use of a legacy barcode scanner, which operates as a standard [PS/2 keyboard](http://pinouts.ru/Inputs/KeyboardPC6_pinout.shtml). The Python code reads serial data output by the Arduino as well as manually entered ISBNs, and uses the [ISBNDB API](http://isbndb.com/api/v2/docs) to gather book metadata and pricing information. It stores the results in an SQLite database. It can create a simple HTML catalog table.

The Arduino part is optional - one can enter ISBNs by hand, or use a USB barcode scanner that mimics a keyboard, or use a PS/2 barcode scanner with a PS/2 to USB HID adapter.
