import re

def convert_to_bloomberg_format(input_string):
    """
    Converts an option trade input to Bloomberg query format.
    
    Input format: <Ticker> <Month> <Strike> <Call/Put> OI Change:
    Example: "MU Jan 50 Call OI Change:"
    Output: "MU US 1/16/26 C50 Equity"
    
    Supports regular expiry (Jan, Feb, etc.) and non-regular expiry:
    - <day><month> format: "27Jan" -> uses date from dates.txt but changes day
    - <month><Year> format: "Jan27" -> uses format "1/??/27"
    
    Args:
        input_string (str): The input string in the format specified
        
    Returns:
        str: Bloomberg query format string
    """
    # Read dates from dates.txt and create month mapping
    # The first 12 dates in dates.txt correspond to the 12 months (Jan through Dec)
    month_to_date = {}
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    # Read dates.txt using relative path
    dates_file = 'dates.txt'
    #print(f"Dates file path: {dates_file}")
    
    try:
        with open(dates_file, 'r') as f:
            dates = [line.strip() for line in f if line.strip()]
            #print(f"Dates read from file: {dates}")
            # Map first 12 dates to the 12 months
            for i, date in enumerate(dates[:12]):
                month_to_date[month_names[i]] = date
            #print(f"Month to date mapping: {month_to_date}")
    except FileNotFoundError:
        raise FileNotFoundError(f"dates.txt not found")
    
    # Parse the input string
    # Format: <Ticker> <Month> <Strike> <Call/Put> OI Change:
    parts = input_string.split()
    #print(f"Input string split into parts: {parts}")
    
    if len(parts) < 4:
        raise ValueError(f"Invalid input format. Expected: <Ticker> <Month> <Strike> <Call/Put> OI Change:")
    
    ticker = parts[0]
    month_field = parts[1]
    strike = parts[2]
    option_type = parts[3].lower()  # "Call" or "Put"
    # print(f"Ticker: {ticker}")
    # print(f"Month field: {month_field}")
    # print(f"Strike: {strike}")
    # print(f"Option type (lowercase): {option_type}")
    # print(month_to_date)
    
    # Determine expiration date based on format
    expiration_date = None
    
    # Check if it's a regular month (Jan, Feb, etc.)
    if month_field in month_to_date:
        expiration_date = month_to_date[month_field]
        #print(f"Regular expiry - Expiration date: {expiration_date}")
    
    # Check for <day><month> format (e.g., "27Jan")
    elif re.match(r'^\d+[A-Z][a-z]+$', month_field):
        # Extract day and month
        match = re.match(r'^(\d+)([A-Z][a-z]+)$', month_field)
        if match:
            day = match.group(1)
            month_abbr = match.group(2)
            if month_abbr in month_to_date:
                base_date = month_to_date[month_abbr]
                # Parse base date (format: M/D/YY or MM/D/YY or M/DD/YY or MM/DD/YY)
                date_parts = base_date.split('/')
                month_num = date_parts[0]
                year = date_parts[2]
                expiration_date = f"{month_num}/{day}/{year}"
                #print(f"Non-regular expiry <day><month> - Expiration date: {expiration_date}")
            else:
                raise ValueError(f"Invalid month abbreviation: {month_abbr}")
    
    # Check for <month><Year> format (e.g., "Jan27")
    elif re.match(r'^[A-Z][a-z]+\d+$', month_field):
        # Extract month and year
        match = re.match(r'^([A-Z][a-z]+)(\d+)$', month_field)
        if match:
            month_abbr = match.group(1)
            year = match.group(2)
            if month_abbr in month_to_date:
                # Get month number from the base date
                base_date = month_to_date[month_abbr]
                month_num = base_date.split('/')[0]
                expiration_date = f"{month_num}/??/{year}"
                #print(f"Non-regular expiry <month><Year> - Expiration date: {expiration_date}")
            else:
                raise ValueError(f"Invalid month abbreviation: {month_abbr}")
    
    else:
        raise ValueError(f"Invalid month format: {month_field}")
    
    # Convert Call/Put to C/P
    option_letter = 'C' if option_type == 'call' else 'P'
    #print(f"Option letter: {option_letter}")
    
    # Construct Bloomberg format: <Ticker> US <Date> <C/P><Strike> Equity
    bloomberg_query = f"{ticker} US {expiration_date} {option_letter}{strike} Equity"
    #print(f"Bloomberg query: {bloomberg_query}")
    
    return bloomberg_query


def process_file_to_bloomberg(input_file, output_file):
    """
    Processes a text file containing multiple option trades and converts them to Bloomberg format.
    
    Args:
        input_file (str): Path to the input text file containing option trades (one per line)
        output_file (str): Path to the output text file where Bloomberg formatted lines will be written
        
    Returns:
        None: Writes results to output_file
    """
    bloomberg_lines = []
    
    try:
        with open(input_file, 'r') as f:
            lines = f.readlines()
        
        print(f"Processing {len(lines)} lines...")
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            
            try:
                bloomberg_format = convert_to_bloomberg_format(line)
                bloomberg_lines.append(bloomberg_format)
            except Exception as e:
                # Log error but continue processing other lines
                print(f"Error processing line {line_num}: {line}")
                print(f"  Error: {e}")
                # Optionally, you could write an error line or skip it
                # bloomberg_lines.append(f"# ERROR: {line} - {e}")
        
        # Write all converted lines to output file
        with open(output_file, 'w') as f:
            for bloomberg_line in bloomberg_lines:
                f.write(bloomberg_line + '\n')
        
        print(f"\nProcessed {len(bloomberg_lines)} lines successfully.")
        print(f"Output written to: {output_file}")
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")
    except Exception as e:
        raise Exception(f"Error processing file: {e}")


def sort_and_group_by_ticker(input_file, output_file):
    """
    Processes the output file from process_file_to_bloomberg() by:
    1. Sorting lines alphabetically (by ticker, which comes first)
    2. Grouping consecutive lines with the same ticker
    3. Inserting an empty line between different tickers with count information
    
    Args:
        input_file (str): Path to the Bloomberg formatted file (output from process_file_to_bloomberg)
        output_file (str): Path to the output text file where sorted and grouped lines will be written
        
    Returns:
        None: Writes results to output_file
    """
    try:
        # Read all lines from input file
        with open(input_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        
        
        # Group lines by ticker and build output
        output_lines = []
        current_ticker = None
        ticker_lines = []
        
        for line in lines:
            # Extract ticker (first word before space)
            ticker = line.split()[0] if line.split() else ""
            
            # If we encounter a new ticker
            if ticker != current_ticker:
                # If we had a previous ticker, add its lines and count
                if current_ticker is not None:
                    # Add all lines for the previous ticker
                    output_lines.extend(ticker_lines)
                    # Add empty line with count
                    output_lines.append(f"{len(ticker_lines)} occurrences of {current_ticker}")
                    output_lines.append("")  # Empty line separator
                
                # Start new ticker group
                current_ticker = ticker
                ticker_lines = [line]
            else:
                # Same ticker, add to current group
                ticker_lines.append(line)
        
        # Add lines and count for the last ticker group
        if current_ticker is not None:
            output_lines.extend(ticker_lines)
            output_lines.append(f"{len(ticker_lines)} occurrences of {current_ticker}")
        
        # Write to output file
        with open(output_file, 'w') as f:
            for output_line in output_lines:
                f.write(output_line + '\n')
        
        print(f"\nSorted and grouped {len(lines)} lines by ticker.")
        print(f"Output written to: {output_file}")
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")
    except Exception as e:
        raise Exception(f"Error processing file: {e}")


# Example usage
if __name__ == "__main__":
    process_file_to_bloomberg("filtered_input.txt", "output.txt")
    sort_and_group_by_ticker("output.txt", "output_processed.txt")

