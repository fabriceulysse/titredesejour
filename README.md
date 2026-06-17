# Classroom Hangman 🎯

A simple, self-contained **Hangman** game built for the classroom. It's a single
HTML file — no installation, no internet, no accounts. Just open it in any web
browser and play, on a laptop, projector, smartboard, or tablet.

## How to play it in class

1. Open **`index.html`** in any web browser (double-click it, or drag it into a
   browser tab).
2. Click **⛶ Fullscreen** for a clean projector view.
3. Students guess letters by **typing** or by **clicking/tapping** the on-screen
   keyboard. 6 wrong guesses and the drawing is complete!
4. Press **Enter** (or click **↻ New word**) for the next word.

## Features for teachers

- **Use your own words.** Click **✏️ Custom words** and paste a list — perfect
  for spelling lists, vocabulary, or topic terms. One word or phrase per line,
  with an optional hint after a `|`:

  ```
  photosynthesis | how plants make food
  the water cycle | evaporation, condensation, precipitation
  métamorphose | la transformation de la chenille
  ```

  Phrases with spaces and punctuation work fine. Your custom list is remembered
  on that computer.

- **Built-in word sets:** Animals, Countries, Food, Sports, Science, Jobs, and
  School Subjects — each word comes with a hint.

- **🔒 Secret word mode.** One student types a secret word (it stays hidden on
  screen) for the rest of the class to guess. Great two-player / team game.

- **💡 Hints** can be turned on for the whole class, or revealed on demand with
  the "Show hint" link — handy for differentiation.

- **Accent-friendly.** Pressing **E** matches **é, è, ê**, so it works for
  language classes too. (e.g. *café* is guessed with C-A-F-E.)

- **Scoreboard** tracks class wins vs. losses, and **🔊 Sound** can be toggled.

## Customising the built-in word lists

Open `index.html` in any text editor and edit the `WORD_SETS` object near the top
of the `<script>` section. Each entry is `["word", "optional hint"]`. You can add,
remove, or rename whole categories.

## No setup required

Everything runs in the browser from the one file. Nothing is sent anywhere; it
works completely offline.
