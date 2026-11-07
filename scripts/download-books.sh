#!/usr/bin/env bash
# Download public-domain books into $ARK_DATA/books for Kavita (a few hundred MB at most).
# Layout: books/<Library>/<Title>/<Title>.epub   (in Kavita, add each Library folder as a library)
#
# Not on Project Gutenberg, so add these by hand (drop the file into a folder like the ones below):
#   The Book of Five Rings, Hagakure, the American Standard Version Bible,
#   Seneca's Letters, Hesperian "Where There Is No Doctor" / "No Dentist" (free PDFs from hesperian.org),
#   "Lessons in Electric Circuits" (free PDFs), factory service manuals for your vehicles.
#   Defensive Tactics: MCRP 3-10A.4 Marine Rifle Squad (marines.mil blocks scripted downloads; save it
#   from a browser: https://www.marines.mil/Portals/1/Publications/MCRP%203-10A.4.pdf).
#   Books you've bought go in the same folders; they stay on your Ark only.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
BOOKS="${ARK_DATA:-/srv/ark}/books"

# Library | Gutenberg ID | Title   (IDs checked 2026-11-05)
GUTENBERG=(
  "Faith|10|King James Bible"
  "Faith|8294|World English Bible"
  "Japanese Philosophy|12096|Bushido, the Soul of Japan (Nitobe)"
  "Japanese Philosophy|769|The Book of Tea (Okakura)"
  "Eastern Philosophy|216|Tao Te Ching (Legge)"
  "Eastern Philosophy|3330|The Analects of Confucius"
  "Eastern Philosophy|132|The Art of War (Sun Tzu)"
  # Western: Greek and Roman classics plus the English-speaking tradition
  "Western Philosophy|1497|The Republic (Plato)"
  "Western Philosophy|1656|Apology (Plato)"
  "Western Philosophy|1600|Symposium (Plato)"
  "Western Philosophy|8438|Nicomachean Ethics (Aristotle)"
  "Western Philosophy|6762|Politics (Aristotle)"
  "Western Philosophy|2680|Meditations (Marcus Aurelius)"
  "Western Philosophy|45109|The Enchiridion (Epictetus)"
  "Western Philosophy|2130|Utopia (More)"
  "Western Philosophy|3207|Leviathan (Hobbes)"
  "Western Philosophy|7370|Second Treatise of Government (Locke)"
  "Western Philosophy|9662|An Enquiry Concerning Human Understanding (Hume)"
  "Western Philosophy|34901|On Liberty (Mill)"
  "Western Philosophy|2944|Essays, First Series (Emerson)"
  "Western Philosophy|205|Walden and Civil Disobedience (Thoreau)"
  "Western Philosophy|5827|The Problems of Philosophy (Russell)"
  # European: continental thinkers (France, Germany, Italy, the Netherlands)
  "European Philosophy|1232|The Prince (Machiavelli)"
  "European Philosophy|3600|Essays (Montaigne)"
  "European Philosophy|59|Discourse on the Method (Descartes)"
  "European Philosophy|18269|Pensees (Pascal)"
  "European Philosophy|3800|Ethics (Spinoza)"
  "European Philosophy|19942|Candide (Voltaire)"
  "European Philosophy|46333|The Social Contract and Discourses (Rousseau)"
  "European Philosophy|4280|Critique of Pure Reason (Kant)"
  "European Philosophy|10741|The Wisdom of Life (Schopenhauer)"
  "European Philosophy|1998|Thus Spake Zarathustra (Nietzsche)"
  "European Philosophy|4363|Beyond Good and Evil (Nietzsche)"
)

# Library | URL | Title
OTHER=(
  "Manuals|https://archive.org/download/Fm21-76SurvivalManual/FM21-76_SurvivalManual.pdf|FM 21-76 US Army Survival Manual"
  # Defensive Tactics: official, Distribution A (approved for public release)
  "Defensive Tactics|https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN38160-FM_3-90-000-WEB-1.pdf|FM 3-90 Tactics (2023)"
  "Defensive Tactics|https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN44065-ATP_3-21.8-001-WEB-3.pdf|ATP 3-21.8 Infantry Rifle Platoon and Squad (2024, Change 1 2025)"
)

get() {  # library url title ext
  local dir="$BOOKS/$1/$3" f
  f="$dir/$3.$4"
  [ -s "$f" ] && { echo "  have  $3"; return; }
  mkdir -p "$dir"
  echo "  get   $3"
  curl -fsSL --retry 3 -o "$f.part" "$2" && mv "$f.part" "$f" || { echo "  !! failed: $2"; rm -f "$f.part"; }
  sleep 2   # be polite to Gutenberg
}

for row in "${GUTENBERG[@]}"; do
  IFS='|' read -r lib id title <<<"$row"
  get "$lib" "https://www.gutenberg.org/ebooks/$id.epub3.images" "$title" epub
done
for row in "${OTHER[@]}"; do
  IFS='|' read -r lib url title <<<"$row"
  get "$lib" "$url" "$title" pdf
done
du -sh "$BOOKS"
