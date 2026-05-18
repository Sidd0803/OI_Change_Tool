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
    month_to_date = {}
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    with open('dates.txt', 'r') as f:
        dates = [line.strip() for line in f if line.strip()]
        for i, date in enumerate(dates[:12]):
            month_to_date[month_names[i]] = date

    parts = input_string.split()

    if len(parts) < 4:
        raise ValueError(f"Invalid input format. Expected: <Ticker> <Month> <Strike> <Call/Put> OI Change:")

    ticker = parts[0]
    month_field = parts[1]
    strike = parts[2]
    option_type = parts[3].lower()

    expiration_date = None

    if month_field in month_to_date:
        expiration_date = month_to_date[month_field]

    elif re.match(r'^\d+[A-Z][a-z]+$', month_field):
        match = re.match(r'^(\d+)([A-Z][a-z]+)$', month_field)
        if match:
            day = match.group(1)
            month_abbr = match.group(2)
            if month_abbr in month_to_date:
                base_date = month_to_date[month_abbr]
                date_parts = base_date.split('/')
                month_num = date_parts[0]
                year = date_parts[2]
                expiration_date = f"{month_num}/{day}/{year}"
            else:
                raise ValueError(f"Invalid month abbreviation: {month_abbr}")

    elif re.match(r'^[A-Z][a-z]+\d+(st|nd|rd|th)$', month_field):
        match = re.match(r'^([A-Z][a-z]+)(\d+)(?:st|nd|rd|th)$', month_field)
        if match:
            month_abbr = match.group(1)
            day = match.group(2)
            if month_abbr in month_to_date:
                base_date = month_to_date[month_abbr]
                date_parts = base_date.split('/')
                month_num = date_parts[0]
                year = date_parts[2]
                expiration_date = f"{month_num}/{day}/{year}"
            else:
                raise ValueError(f"Invalid month abbreviation: {month_abbr}")

    elif re.match(r'^[A-Z][a-z]+\d+$', month_field):
        match = re.match(r'^([A-Z][a-z]+)(\d+)$', month_field)
        if match:
            month_abbr = match.group(1)
            year = match.group(2)
            if month_abbr in month_to_date:
                base_date = month_to_date[month_abbr]
                month_num = base_date.split('/')[0]
                expiration_date = f"{month_num}/??/{year}"
            else:
                raise ValueError(f"Invalid month abbreviation: {month_abbr}")

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
