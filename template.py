import re
def template(input_file, output_file):
    """
    Filters lines from an input file that contain "OI Change" (case-insensitive)
    and writes them to an output file.
    
    Args:
        input_file (str): Path to the input text file
        output_file (str): Path to the output text file where filtered lines will be written
        
    Returns:
        int: Number of lines written to output file
    """
    filtered_lines = []
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Write new lines to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')
                # add substring
                substr = match.group() if (match := re.search(r'^.*?(Put|Call|PS|CS|RR)', line)) else ''
                f.write(substr + '\n')
                f.write("---------------------------------"+'\n')

        
        print(f"Filtered {len(filtered_lines)} lines containing 'OI Change'")
        print(f"Output written to: {output_file}")
        
        return len(filtered_lines)
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")
    except Exception as e:
        raise Exception(f"Error processing file: {e}")


# Example usage
if __name__ == "__main__":
    input_file = "original_input.txt"
    output_file = "template.txt"
    template(input_file, output_file)
