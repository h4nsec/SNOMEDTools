import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import csv
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import pandas as pd
import re

# Optionally disable SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Add messages to the scrolling text area
def add_log(message):
    text_area.insert(tk.END, message + "\n")
    text_area.see(tk.END)  # Auto-scroll to the bottom
    root.update()  # Update GUI to refresh text_area content

# Function to load a file and process it (Deconstruct)
def load_file():
    file_path = filedialog.askopenfilename(filetypes=[("TSV files", "*.tsv")])
    if file_path:
        add_log(f"Loaded file: {file_path}")
        process_file(file_path)

# Function to strip post-coordinated expressions and remove extra spaces
def strip_post_coordinated_expression(expression):
    # Remove descriptions, spaces, and only keep numeric IDs and structure
    stripped_expression = re.sub(r'\|\s*[^|]+\s*\|', '', expression)
    # Remove extra spaces outside of numbers, brackets, etc.
    stripped_expression = re.sub(r'\s+', '', stripped_expression)
    return stripped_expression

# Function to strip expressions dynamically
def strip_file():
    file_path = filedialog.askopenfilename(filetypes=[("TSV files", "*.tsv")])
    if not file_path:
        return

    # Load the TSV file into a DataFrame
    df = pd.read_csv(file_path, delimiter='\t', encoding='utf-8', on_bad_lines='skip', engine='python')

    # Check if the required column is present
    if "Post_Coordinated_Expression" not in df.columns:
        add_log("Error: 'Post_Coordinated_Expression' column not found in the TSV file.")
        return

    # Apply the stripping function to create a new column
    df['Post_Coordinated_Expression_Stripped'] = df['Post_Coordinated_Expression'].fillna('').astype(str).apply(strip_post_coordinated_expression)

    # Save the modified DataFrame to a new TSV file
    output_path = file_path.replace('.tsv', '_stripped.tsv')
    df.to_csv(output_path, sep='\t', index=False)

    add_log(f"Stripped file saved as {output_path}")
    messagebox.showinfo("Strip Complete", f"Stripped file saved as {output_path}")

# Function to process the file (Deconstruct)
def process_file(file_path):
    output_path = file_path.replace('.tsv', '_processed.tsv')
    with open(file_path, 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter='\t')
        base_fieldnames = reader.fieldnames[:]  # Copy of original fieldnames
        extended_fieldnames = set(base_fieldnames)  # Use a set to track what's been added

        rows = []
        all_json_fieldnames = []  # To track the order of JSON-derived fields

        for row in reader:
            target_code = row.get('Target code')
            url = f"https://snowstorm-test.msal.gob.ar/MAIN/concepts/{target_code}/authoring-form"
            add_log(f"Fetching data for code: {target_code}")
            try:
                response = requests.get(url, verify=False)
                response.raise_for_status()
                json_data = response.json()
                json_parsed_data = parse_json_data(json_data)

                # Collecting new fieldnames in order
                for key in json_parsed_data.keys():
                    if key not in extended_fieldnames:
                        extended_fieldnames.add(key)
                        all_json_fieldnames.append(key)

                row.update(json_parsed_data)
                rows.append(row)
                add_log(f"Data formatted successfully for code: {target_code}")
            except requests.RequestException as e:
                error_key = 'Error'
                row[error_key] = str(e)
                if error_key not in extended_fieldnames:
                    extended_fieldnames.add(error_key)
                    all_json_fieldnames.append(error_key)
                rows.append(row)
                add_log(f"Failed to fetch data for code: {target_code}: {str(e)}")

        final_fieldnames = base_fieldnames + all_json_fieldnames  # Merge with JSON fieldnames in order

        with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=final_fieldnames, delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)

        add_log(f"Process complete. Processed file saved as {output_path}")
        messagebox.showinfo("Process Complete", f"Processed file saved as {output_path}")

# Function to parse JSON data for Deconstruct
def parse_json_data(json_data):
    output_data = {}
    # Extracting and formatting concepts
    for i, concept in enumerate(json_data.get('concepts', []), start=1):
        output_data[f"Concept_{i}_ID"] = concept['id']
        output_data[f"Concept_{i}_Primitive"] = concept['primitive']
        output_data[f"Concept_{i}_Term"] = concept['term']

    # Extracting and formatting groups and attributes
    for i, group in enumerate(json_data.get('groups', []), start=1):
        for j, attr in enumerate(group.get('attributes', []), start=1):
            output_data[f"Group_{i}_Attr_{j}_Type_Term"] = attr['type']['term']
            output_data[f"Group_{i}_Attr_{j}_Type_ID"] = attr['type']['id']
            output_data[f"Group_{i}_Attr_{j}_Target_Term"] = attr['target']['term']
            output_data[f"Group_{i}_Attr_{j}_Target_ID"] = attr['target']['id']

    return output_data

# Function to validate SNOMED CT expressions and summarize the results
def validate_file():
    file_path = filedialog.askopenfilename(
        filetypes=[("TSV files", "*.tsv"), ("All files", "*.*")]
    )
    if not file_path:
        return

    # Load the TSV file into a DataFrame
    df = pd.read_csv(file_path, delimiter='\t')

    # Check if the required column is present
    if "Post_Coordinated_Expression" not in df.columns:
        add_log("Error: 'Post_Coordinated_Expression' column not found in the TSV file.")
        return

    # Initialize counters
    total_expressions = len(df)
    valid_count = 0
    invalid_count = 0

    # Define the OntoServer URL and other parameters
    url = "https://r4.ontoserver.csiro.au/fhir/CodeSystem/$validate-code"
    system = "http://snomed.info/sct"

    # HTTP headers for validation
    headers = {
        'Accept': 'application/fhir+json',
        'Content-Type': 'application/fhir+json'
    }

    # Validate each expression
    for index, expression in enumerate(df["Post_Coordinated_Expression"]):
        params = {
            'url': system,
            'code': expression,
            'system': system
        }
        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            json_response = response.json()
            result = next((param["valueBoolean"] for param in json_response["parameter"] if param["name"] == "result"), False)

            if result:
                validation_message = f"Row {index + 1}: Expression is valid."
                valid_count += 1
            else:
                validation_message = f"Row {index + 1}: Expression is not valid."
                invalid_count += 1
        else:
            validation_message = f"Row {index + 1}: Server error - {response.text}"
            invalid_count += 1

        # Display individual validation results in the scrolled text area
        add_log(validation_message)

    # Display summary results
    summary_message = (f"Total expressions processed: {total_expressions}\n"
                       f"Valid expressions: {valid_count}\n"
                       f"Invalid expressions: {invalid_count}")
    add_log(summary_message)
    messagebox.showinfo("Validation Summary", summary_message)


# Create the root window
root = tk.Tk()
root.title("SNOMED Tools")

# Create the main canvas
canvas = tk.Canvas(root, height=100, width=500)
canvas.pack()

# Add a scrolled text area
text_area = scrolledtext.ScrolledText(root, height=30)
text_area.pack(pady=10)

# Create a frame for the buttons to be placed horizontally
button_frame = tk.Frame(root)
button_frame.pack(pady=10)

# Add buttons to the frame
# Deconstruct the Pre-Coordinated Expressions
open_file_btn = tk.Button(button_frame, text="Deconstruct", padx=10, pady=5, fg="white", bg="#263D42", command=load_file)
open_file_btn.pack(side="left", padx=5)

# Strip the non required chars for validation
strip_btn = tk.Button(button_frame, text="Strip", padx=10, pady=5, fg="white", bg="#263D42", command=strip_file)
strip_btn.pack(side="left", padx=5)

# Validate the SNOMED Post coordinated expressions
validate_btn = tk.Button(button_frame, text="Validate", padx=10, pady=5, fg="white", bg="#263D42", command=validate_file)
validate_btn.pack(side="left", padx=5)


close_btn = tk.Button(button_frame, text="Close", padx=10, pady=5, fg="white", bg="#263D42", command=root.quit)
close_btn.pack(side="left", padx=5)

# Run the main loop
root.mainloop()
