#!/usr/bin/env python3
"""
Guess the words, on the command line.
"""

import argparse
import curses
import math
import os
import random
import time

# ============================================================================

class QuitException(Exception):
    """
    How we quit the round.
    """
    pass


class WordGuess():
    """
    Guess the word!
    """
    # Colour pair indices, start at 1 since 0 is reserved
    _EMPTY_PAIR   = 1
    _BOARD_PAIR   = 2
    _GUESS_PAIR   = 3
    _MISS_PAIR    = 4
    _PARTIAL_PAIR = 5
    _EXACT_PAIR   = 6
    _MESSAGE_PAIR = 7

    # Text constants
    _TITLE  = "Word Guess!"
    _EMPTY  = '?'
    _ESCAPE =  27 # ASCII value
    _DEL    = 127 # ASCII value

    # Placement of things
    _BOARD_TOP      = 5 # From the top
    _MESSAGE_OFFSET = 4 # From the bottom of the board

    # Rot13'd offensive words. Some more offensive than others. Basically things
    # which we just want to avoid...
    _OFFENSIVE_WORDS = (
        "NANY", "NAHF", "NEFR", "NFF", "NFFUNG", "OYNPXONYY", "OYNPXYVFG",
        "OVGPU", "OYBJWBO", "OBBOF", "OHTTRE", "PUVAX", "PUVAXL", "PYVG",
        "PYVGBEVF", "PYVGF", "PBPX", "PBBA", "PBPXFHPXRE", "PENC", "PHZ",
        "PHZZVAT", "PHZF", "PHAAVYVATHF", "PHAG", "PHAGRQ", "PHAGF", "QVPX",
        "QVPXF", "QBTTVAT", "QBAT", "QBBPU", "RWNPHYNGR", "RWNPHYNGRQ",
        "RWNPHYNGRF", "RWNPHYNGVAT", "RWNPHYNGVATF", "RWNPHYNGVBA", "SNT",
        "SNTTBG", "SRYPU", "SRYPUVAT", "SRYYNGR", "SRYYNGVB", "SVFGVAT", "SHPX",
        "SHPXRQ", "SHPXRE", "SHPXVAT", "SHPXF", "TNATONAT", "TNLYBEQ", "TLC",
        "TLCCRQ", "UBZB", "UBEAL", "VAPRFG", "WNC", "WVMM", "ZNFGHEONGR", "ANMV",
        "ARTEB", "ARTEBF", "AVTTRE", "AVCCYR", "AVCCYRF", "AVC", "BETNFZ",
        "BETNFZF", "BETL", "CNRQB", "CRAVF", "CVFF", "CBBS", "CBEA", "CBEAB",
        "CEVPX", "CEVPXF", "CHOR", "CHORF", "CHFFL", "CHFFVRF", "DHRRE", "DHRREF",
        "DHVZ", "ENCR", "ENCRF", "ENCVAT", "ENCVFG", "FPEBGHZ", "FRZRA", "FRK",
        "FRKL", "FUNT", "FUNTTVAT", "FUVG", "FUVGF", "FUVGGL", "FUNG", "FYNIR",
        "FYHG", "FYHGF", "FBQBZVMR", "FBQBZBL", "FCHAX", "GVGF", "GVGGVRF",
        "GVGGL", "GBCYRFF", "GENAAL", "GJNG", "HCFXVEG", "INTVAN", "IHYIN",
        "IVETVA", "JNAX",
    )

    # ------------------------------------------------------------------------

    def __init__(self,
                 length     : int,
                 tries      : int,
                 words_file : str,
                 accessible : bool,
                 accented   : bool) -> None:
        """
        Set up the game
        """
        print()
        print("Setting up WordGuess...")

        # Save params
        self._length     = length
        self._tries      = tries
        self._accessible = accessible

        # Curses params
        self._scr   = None
        self._max_x = None
        self._max_y = None

        # The set of letters which we know about. We ignore letters which are
        # not in this set since they can be sent as control chars by the
        # terminal and misinterpreted.
        self._letters = set()

        # Read in the dictionary of words
        self._words = []
        self._all_words = set()
        print(f"  Loading dictionary from {words_file}")
        with open(words_file, 'rb') as fh:
            for line in fh.readlines():
                # Read
                try:
                    word = line.decode()
                except UnicodeDecodeError:
                    pass

                # Tidy to be like we like it
                word = word.strip()
                WORD = word.upper()

                # Remember this in self._all_words since we need to care about them
                # for checking plurals etc.
                self._all_words.add(WORD)

                # Print out progress. Printing is _slow_ so not too much.
                count = len(self._all_words)
                if count & 0x3ff == 0:
                    print(f"  Loaded {count} words\r", end='', flush=True)

                # Ignore proper names and abbreviations, these will start with a
                # capital letter
                if len(word) > 0 and 'A' <= word[0] <= 'Z':
                    continue

                # Now we want it all uppercase
                word = WORD

                # Check that it's what we want. We avoid offensive words and
                # ones which look like they are plurals, past tense, etc. Some
                # of this will general false positives but that's not the end of
                # the world.
                if (self._rot13upper(word) not in self._OFFENSIVE_WORDS and
                    word.isalpha()                                      and
                    len(word) == length                                 and
                    (accented or all('A' <= c <= 'Z' for c in word))    and
                    not (word[-1:] in [ 'D',  'R',  'S', 'Y'] and
                         word[:-1] in self._all_words)                  and
                    not (word[-2:] in ['ED', 'ER', 'ES', 'LY'] and
                         word[:-2] in self._all_words)                  and
                    not (word[-3:] in [ 'IES',  'IED', 'IER', 'ING'] and
                         (word[:-3] + 'Y') in self._all_words)          and
                    not (word[-3:] == 'ING' and
                         ((word[:-3])       in self._all_words or
                          (word[:-3] + 'E') in self._all_words))):
                    # This is a word which we want so we remember it
                    self._words.append(word)

                    # And save all its letters in the set of known ones
                    self._letters.update(word)

        print("  Loading done!")

        # All the letters, but in sorted order
        self._sorted_letters = sorted(self._letters)

        # Anything?
        if len(self._words) == 0:
            raise ValueError(
                "No words of length {} found in '{}'".format(
                    self._length, words_file
                )
            )


    def init(self):
        """
        Set up the game.
        """
        # Init curses
        os.environ['ESCDELAY'] = '1' # Deliver Esc right away
        self._scr = curses.initscr()
        curses.start_color()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(False)
        self._scr.keypad(True)

        # Display dimensions
        (self._max_y, self._max_x) = self._scr.getmaxyx()

        # Set up the colour pairs; zero is reserved. Hopefully these are okay
        # for red/green colour blind people.
        curses.init_pair(self._EMPTY_PAIR,   curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(self._BOARD_PAIR,   curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(self._GUESS_PAIR,   curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(self._MESSAGE_PAIR, curses.COLOR_WHITE, curses.COLOR_BLACK)
        if self._accessible:
            curses.init_pair(self._MISS_PAIR,    curses.COLOR_WHITE, curses.COLOR_BLUE   )
            curses.init_pair(self._PARTIAL_PAIR, curses.COLOR_WHITE, curses.COLOR_CYAN   )
            curses.init_pair(self._EXACT_PAIR,   curses.COLOR_WHITE, curses.COLOR_MAGENTA)
        else:
            curses.init_pair(self._MISS_PAIR,    curses.COLOR_WHITE, curses.COLOR_RED  )
            curses.init_pair(self._PARTIAL_PAIR, curses.COLOR_WHITE, curses.COLOR_BLUE )
            curses.init_pair(self._EXACT_PAIR,   curses.COLOR_WHITE, curses.COLOR_GREEN)


    def play(self) -> None:
        """
        Play the game.
        """
        won  = 0
        lost = 0
        while True:
            # Draw the board
            self._draw_board()

            # Show the current score
            score = f'Won {won}  Lost {lost}'
            self._scr.addstr(
                self._BOARD_TOP + self._tries + 2,
                (self._max_x - len(score) - 1) // 2,
                score,
                curses.color_pair(self._MESSAGE_PAIR)
            )

            # And play
            try:
                # Choose a word to play with
                word = random.choice(self._words)

                # And play the game
                if self._play_round(word):
                    self._message("You guessed correctly!")
                    won += 1
                else:
                    self._message(f"Sorry, you didn't guess; it was '{word}'...")
                    lost += 1

            except QuitException:
                return

            # Wait for the player to press a key. If it's escape then be done.
            if self._scr.getch() == self._ESCAPE:
                return


    def _play_round(self,
                    word : str) -> bool:
        """
        Play a round of the game.

        :param word: The word to guess.
        """
        # Draw the screen
        for y in range(0, self._tries):
            for x in range(0, self._length):
                self._set_board_char(x, y, self._EMPTY, self._EMPTY_PAIR)

        # Say we're ready to go
        self._message("Guess the word!")

        # Current player position, (x,y)
        position = [0, 0]

        # The current guess
        guess = [self._EMPTY] * self._length

        # The info letters
        info_letters = dict()

        # Keep going until the user has guessed
        while position[1] < self._tries:
            key = -1
            while key == -1:
                key = self._scr.getch()

            # Blank out the message now that we're doing something
            self._message('')

            # What did we get?
            if key == self._ESCAPE:
                raise QuitException()

            if key in (curses.KEY_BACKSPACE, curses.KEY_DC, self._DEL):
                if position[0] > 0:
                    # Move the position back one, ensure that the new spot is
                    # blank
                    position[0] -= 1
                    guess[position[0]] = self._EMPTY
                    self._set_board_char(position[0],
                                         position[1],
                                         guess[position[0]],
                                         self._EMPTY_PAIR)

            elif position[0] < self._length:
                # We're in the guessing phase here

                # Whether we move on after displaying the char
                move = False

                # Okay, this is likely someone entering a character which is
                # part of their guess for the word
                try:
                    # Turn it into a character and see if we want to use it
                    char = chr(key).upper()
                    if (len(char) == 1 and
                        char.isalpha() and
                        char in self._letters):
                        # Put in the letter
                        guess[position[0]] = char
                        self._set_board_char(position[0],
                                             position[1],
                                             guess[position[0]],
                                             self._GUESS_PAIR)

                        # And move on
                        position[0] += 1

                except ValueError:
                    # Ignore
                    pass

            elif key == curses.KEY_ENTER or key == ord('\n'):
                # All the guess letters are filled in and the user is guessing

                # See if it's a word which we know
                guessed = ''.join(guess)
                if guessed not in self._all_words:
                    self._message(f'"{guessed}" is not a known word')
                    curses.beep()
                    continue

                # It's a word we know, see if it's a match
                letters = list(word)
                pairs   = [self._MISS_PAIR] * self._length

                # First look for exact matches
                for i in range(self._length):
                    # Colour the guess accordingly
                    if guess[i] == word[i]:
                        # Exact match
                        pairs[i] = self._EXACT_PAIR

                        # Blank it out so that it's removed from further match
                        # attempts. This disambiguates a second occurance saying
                        # it matched "somewhere".
                        letters[i] = None

                    else:
                        # Not an exact match
                        match = False

                # Now look for partial matches
                for i in range(self._length):
                    # Avoid what has been guessed
                    if pairs[i] == self._EXACT_PAIR:
                        continue

                    # Else look for it
                    try:
                        # Look for it
                        index = letters.index(guess[i])

                        # If we found it _somewhere_ then this was a partial match
                        pairs[i] = self._PARTIAL_PAIR

                        # And blank, for the same reasons as above
                        letters[index] = None

                    except ValueError:
                        # Nothing to do
                        pass

                # Now paint the board and the info section
                for i in range(self._length):
                    # Update the board
                    self._set_board_char(i,
                                         position[1],
                                         guess[i],
                                         pairs[i])

                    # And the info letters
                    if ((pairs[i] == self._EXACT_PAIR) or
                        (pairs[i] == self._PARTIAL_PAIR and
                         info_letters.get(guess[i], None) != self._EXACT_PAIR) or
                        (pairs[i] == self._MISS_PAIR and
                         guess[i] not in info_letters)):
                        info_letters[guess[i]] = pairs[i]
                    self._set_info_letter(guess[i], info_letters[guess[i]])

                    # And wait a bit
                    time.sleep(0.1)

                # Done?
                if all((p == self._EXACT_PAIR) for p in pairs):
                    return True
                else:
                    # And move to the next try
                    position[0]  = 0
                    position[1] += 1
                    guess        = [self._EMPTY] * self._length

        # If we got here then then user didn't guess correctly in the allotted
        # number of tries
        return False


    def quit(self) -> None:
        # Tidy up curses and return the terminal to normal use
        self._scr.keypad(False)
        curses.nocbreak()
        curses.echo()
        curses.curs_set(True)
        curses.endwin()

        print("Shutting down WordGuess.")
        print()


    def _draw_board(self):
        """
        Draw the board, ready for play
        """
        # Start blank
        self._scr.clear()

        # Draw the title
        x = (self._max_x - len(self._TITLE) - 1) // 2
        self._scr.addstr(
            1, x, self._TITLE, curses.color_pair(self._MESSAGE_PAIR)
        )
        self._scr.addstr(
            2, x, '=' * len(self._TITLE), curses.color_pair(self._MESSAGE_PAIR)
        )

        # The board outline
        dx = self._max_x // 2 - self._length - 1
        dy = self._BOARD_TOP
        self._scr.addstr(
            self._BOARD_TOP - 1, dx, '/' + '-' * (self._length * 2 - 1) + '\\',
            curses.color_pair(self._BOARD_PAIR)
        )
        for i in range(self._tries):
            for j in range(self._length + 1):
                self._scr.addstr(
                    self._BOARD_TOP + i, dx + 2 * j, '|' ,
                    curses.color_pair(self._BOARD_PAIR)
                )
        self._scr.addstr(
            self._BOARD_TOP + self._tries, dx, '\\' + '-' * (self._length * 2 - 1) + '/',
            curses.color_pair(self._BOARD_PAIR)
        )

        # The info chars
        for letter in self._sorted_letters:
            self._set_info_letter(letter, self._EMPTY_PAIR)


    def _set_board_char(self,
                        x         : int,
                        y         : int,
                        character : str,
                        pair      : int):
        """
        Set a character using the given params on the board.

        :param x:         The ``x`` coordinate on the grid.
        :param y:         The ``y`` coordinate on the grid.
        :param character: The single character to set.
        :param pair:      The colour pair to use.
        """
        # Determine the x and y for the display
        dx = self._max_x // 2 - self._length + 2 * x
        dy = self._BOARD_TOP + y

        if len(character) == 1:
            # The X and Y are reversed for curses, we do that here.
            self._scr.addstr(dy,
                             dx,
                             character,
                             curses.color_pair(pair))
        self._scr.refresh()


    def _message(self, msg):
        """
        Put a message on the screen.
        """
        # Cut up the message if it wraps and see how to centre it
        width = 0
        lines = []
        while len(msg) > 0:
            part = msg[:self._max_x]
            lines.append(part)
            msg = msg[self._max_x:]
            width = max(width, len(part))

        # Pad out the lines to a block
        offset = self._BOARD_TOP + self._tries + self._MESSAGE_OFFSET
        height = min(self._max_y - offset, 4)
        while len(lines) < height:
            lines.append('')

        # Render it
        for (i, line) in enumerate(lines):
            # We need to pad since otherwise we can leave parts of an old
            # message behind
            pad       = self._max_x - width
            left_pad  = pad // 2
            right_pad = max(0, pad - left_pad - 1)

            # The line we want to render is now this
            line = ' ' * left_pad + line + ' ' * right_pad

            # And place it
            self._scr.addstr(
                offset + i,
                0,
                line, curses.color_pair(self._MESSAGE_PAIR)
            )

        # And display it
        self._scr.refresh()


    def _rot13upper(self, word):
        """
        Do a rot13 on the given word, as uppercase.
        """
        return ''.join(
            chr((ord(c) - ord('A') + 13) % 26 + ord('A'))
            for c in word.upper()
        )


    def _set_info_letter(self, letter, colour_pair):
        """
        Draw the given letter, in the right spot, using the given colour pair.
        """
        # How many letters
        count = len(self._sorted_letters)

        # How much room top to bottom
        max_y = self._tries

        # How many columns on each side? Ensure it's a even number for symmetry.
        num_cols = math.floor(2 * count / max(max_y, 1))
        if num_cols == 0:
            num_cols = 2
        elif num_cols % 2 == 1:
            num_cols -= 1

        # We will draw these and two columns and we want each column set to be a
        # little away from the board (i.e. a bit of padding).
        x_width = 2 * num_cols + int(math.ceil(self._length / 2))
        off_left  = int(math.floor(self._max_x / 2)) - x_width
        off_right = int(math.ceil (self._max_x / 2)) + 3

        # How long should each column be?
        col_length = math.floor(count / num_cols)

        # Figure out the index of our letter in the sorted set
        index = self._sorted_letters.index(letter)

        # The coordinates within the columns
        x = index %  num_cols
        y = index // num_cols

        # We want gaps between the columns
        x *= 2

        # Now place it
        if x < num_cols:
            # Left side
            cx = off_left  + x
        else:
            # Right side
            cx = off_right + x
        cy = self._BOARD_TOP + 2 * y

        # And place it
        self._scr.addstr(cy, cx, letter, curses.color_pair(colour_pair))


# ============================================================================


if __name__ == '__main__':
    # Parse the command line args
    parser = argparse.ArgumentParser(description='Guess the words.')
    parser.add_argument('--accented', action='store_true',
                        help='Allow accented words')
    parser.add_argument('--accessible', action='store_true',
                        help='Change the colours to avoid red/green pairs')
    parser.add_argument('--dictionary', type=str, default='/usr/share/dict/words',
                        help='Path to the dictionary file.')
    parser.add_argument('--length', type=int, default=5,
                        help='The word length')
    parser.add_argument('--tries', type=int, default=6,
                        help='The number of tries')
    args = parser.parse_args()

    game = WordGuess(args.length,
                     args.tries,
                     args.dictionary,
                     args.accessible,
                     args.accented)

    # And play
    exception = None
    try:
        game.init()
        game.play()
    except curses.error as e:
        exception = e
    finally:
        game.quit()

    if exception:
        print("Got an error, is the window big enough?")
