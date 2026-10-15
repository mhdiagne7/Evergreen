"""Export des propositions, avec protection des cellules pour les tableurs."""

import csv
import io


def csv_bytes(rows):
    output = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: safe_cell(value) for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
