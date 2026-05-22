import re


def filter_oi_change_lines(input_file, output_file):
    filtered_lines = []

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        if 'oi change' in line.lower():
            filtered_lines.append(line.rstrip('\n'))

    with open(output_file, 'w', encoding='utf-8') as f:
        for filtered_line in filtered_lines:
            f.write(filtered_line + '\n')

    print(f"Filtered {len(filtered_lines)} lines containing 'OI Change'")
    print(f"Output written to: {output_file}")

    return len(filtered_lines)


def convert_to_bloomberg_format(input_string):
    month_num_to_abbr = {str(i + 1): m for i, m in enumerate(
        ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
         'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    )}

    # (month_lower, year_2dig) -> full date string; month_lower -> earliest date seen
    month_year_to_date = {}
    month_to_first_date = {}

    with open('dates.txt', 'r') as f:
        for line in f:
            date_str = line.strip()
            if not date_str:
                continue
            d = date_str.split('/')
            if len(d) == 3:
                abbr = month_num_to_abbr.get(d[0])
                if abbr:
                    month_year_to_date[f"{abbr}_{d[2]}"] = date_str
                    month_to_first_date.setdefault(abbr, date_str)

    def find_date(month_abbr, year_2dig=None):
        if year_2dig:
            key = f"{month_abbr}_{year_2dig}"
            if key in month_year_to_date:
                return month_year_to_date[key]
            raise ValueError(f"No expiry found for {month_abbr.capitalize()} '{year_2dig}' in dates.txt")
        if month_abbr in month_to_first_date:
            return month_to_first_date[month_abbr]
        raise ValueError(f"No expiry found for {month_abbr.capitalize()} in dates.txt")

    parts = input_string.split()

    if len(parts) < 4:
        raise ValueError(f"Invalid input format. Expected: <Ticker> <Month> <Strike> <Call/Put> OI Change:")

    ticker = parts[0]
    month_field = parts[1]
    strike = parts[2]
    option_type = parts[3].lower()

    expiration_date = None
    mf = month_field.lower()

    # Case 1: plain month, e.g. "Jun" / "jun" / "JUN"
    if re.match(r'^[a-z]+$', mf):
        expiration_date = find_date(mf)

    # Case 2: day + month, e.g. "15Jun"
    elif re.match(r'^\d+[a-z]+$', mf):
        match = re.match(r'^(\d+)([a-z]+)$', mf)
        day, abbr = match.group(1), match.group(2)
        base = find_date(abbr).split('/')
        expiration_date = f"{base[0]}/{day}/{base[2]}"

    # Case 3: month + day + ordinal, e.g. "Jun15th"
    elif re.match(r'^[a-z]+\d+(st|nd|rd|th)$', mf):
        match = re.match(r'^([a-z]+)(\d+)(?:st|nd|rd|th)$', mf)
        abbr, day = match.group(1), match.group(2)
        base = find_date(abbr).split('/')
        expiration_date = f"{base[0]}/{day}/{base[2]}"

    # Case 4: month + 2-digit year, e.g. "Jan27"
    elif re.match(r'^[a-z]+\d+$', mf):
        match = re.match(r'^([a-z]+)(\d+)$', mf)
        abbr, year_2dig = match.group(1), match.group(2)
        expiration_date = find_date(abbr, year_2dig)

    else:
        raise ValueError(f"Invalid month format: {month_field}")

    option_letter = 'C' if option_type == 'call' else 'P'
    return f"{ticker} US {expiration_date} {option_letter}{strike} Equity"


def process_file_to_bloomberg(input_file, output_file):
    bloomberg_lines = []

    with open(input_file, 'r') as f:
        lines = f.readlines()

    print(f"Processing {len(lines)} lines...")
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            bloomberg_lines.append(convert_to_bloomberg_format(line))
        except Exception as e:
            print(f"Error processing line {line_num}: {line}")
            print(f"  Error: {e}")

    with open(output_file, 'w') as f:
        for bloomberg_line in bloomberg_lines:
            f.write(bloomberg_line + '\n')

    print(f"\nProcessed {len(bloomberg_lines)} lines successfully.")
    print(f"Output written to: {output_file}")


def sort_and_group_by_ticker(input_file, output_file):
    with open(input_file, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    output_lines = []
    current_ticker = None
    ticker_lines = []

    for line in lines:
        ticker = line.split()[0] if line.split() else ""

        if ticker != current_ticker:
            if current_ticker is not None:
                output_lines.extend(ticker_lines)
                output_lines.append(f"{len(ticker_lines)} occurrences of {current_ticker}")

            current_ticker = ticker
            ticker_lines = [line]
        else:
            ticker_lines.append(line)

    if current_ticker is not None:
        output_lines.extend(ticker_lines)
        output_lines.append(f"{len(ticker_lines)} occurrences of {current_ticker}")

    with open(output_file, 'w') as f:
        for output_line in output_lines:
            f.write(output_line + '\n')

    print(f"\nSorted and grouped {len(lines)} lines by ticker.")
    print(f"Output written to: {output_file}")


if __name__ == "__main__":
    filter_oi_change_lines("template.txt", "filtered_input.txt")
    process_file_to_bloomberg("filtered_input.txt", "output.txt")
    sort_and_group_by_ticker("output.txt", "output_processed.txt")
