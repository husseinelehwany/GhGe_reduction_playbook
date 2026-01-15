import os
import json
import warnings

class ErrorParser:
    """
    This class reads energyplus errors from the .err file
    parse: reads .err file
    get_severe_fatal: gets severe and fatal errors

    It returns the errors in json format and saves them to json file for future retrieval
    """
    def __init__(self):
        self.errors = []

    def parse(self, dir_path, err_file_name):
        if not err_file_name.endswith('.err'):
            raise ValueError("File must have .err extension")
        error_file = os.path.join(dir_path, err_file_name)  #'eplusout.err'
        with open(error_file, 'r') as f:
            lines = f.readlines()
        current_type = None
        current_content = []
        for line in lines:
            line = line.strip()

            # Check for error type markers
            if '** Warning **' in line:
                # Save previous error if exists
                if current_type and current_content:
                    self.errors.append({
                        "type": current_type,
                        "content": " ".join(current_content)
                    })
                current_content = []
                current_type = "Warning"
                content = line.split('Warning', 1)[1].strip().lstrip('**').strip()
                current_content.append(content)

            elif '** Severe  **' in line:
                if current_type and current_content:
                    self.errors.append({
                        "type": current_type,
                        "content": " ".join(current_content)
                    })
                current_content = []
                current_type = "Severe"
                content = line.split('Severe', 1)[1].strip().lstrip('**').strip()
                current_content.append(content)
            elif '**  Fatal  **' in line:
                if current_type and current_content:
                    self.errors.append({
                        "type": current_type,
                        "content": " ".join(current_content)
                    })
                current_content = []
                current_type = "Fatal"
                content = line.split('Fatal', 1)[1].strip().lstrip('**').strip()
                current_content.append(content)
            elif '~~~' in line and current_type:
                # Extract content after ~~~
                content = line.split('~~~', 1)[1].strip().lstrip('**').strip()
                if content:
                    current_content.append(content)

            # Add the last error
        if current_type and current_content:
            self.errors.append({
                "type": current_type,
                "content": " ".join(current_content)
            })

    def save(self, output_dir, file_name):
        if not file_name.endswith('.json'):
            raise ValueError("file name must end with .json")
        if not self.errors:
            warnings.warn("Errors array is empty! Errors not read yet!")
        with open(os.path.join(output_dir, file_name), 'w') as f:
            json.dump(self.errors, f, indent=2)

    def read_errors_json(self, file_path):
        # reads error from json file, for future retrieval of errors if .err file is not available
        if not file_path.endswith('.json'):
            raise ValueError("reads only .json files")
        with open(file_path, 'r') as f:
            self.errors = json.load(f)

    def get_all_errors(self):
        return self.errors

    def get_warnings(self):
        return [error for error in self.errors if error['type'] == 'Warning']

    def get_severe_fatal(self):
        return [error for error in self.errors if error['type'] in ['Severe', 'Fatal']]

    def delete(self):
        self.errors = []


def main():
    error_parser = ErrorParser()
    error_parser.parse( r"C:\Users\Hussein Elehwany\Desktop\Repos\GhGe_reduction_playbook\ai_for_bem_workflow\results\v37", 'eplusout.err')
    error_parser.save(r"C:\Users\Hussein Elehwany\Desktop\Repos\GhGe_reduction_playbook\ai_for_bem_workflow\results\v37", "errors_json.json")
    if error_parser.get_severe_fatal():
        print(error_parser.get_severe_fatal())
    # error_parser.delete()

if __name__ == "__main__":
    main()