import os
import re
import sys
import json
from PyPDF2 import PdfReader

# api_clients.py sits in the parent folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_clients import OpenRouterAPIClient

DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
SCHEMA_PATH = os.path.join("input_files", "pca_report_schema.json")
OUTPUT_ROOT = r"results\PCA_summaries"


class PCAAnalyzer:
    """
    Reads property condition assessment (PCA) reports, sends the text to an LLM and returns
    the building components, their condition and the recommended actions as structured data.
    """

    def __init__(self, client_type: str = DEFAULT_MODEL, schema_path: str = SCHEMA_PATH):
        """
        Args:
            model_name: OpenRouter model id
            schema_path: json schema of the structured output
        """
        model_name = {"gemini": "google/gemini-3.1-pro-preview",
                        "deepseek": "~deepseek/deepseek-pro-latest",
                        "claude": "anthropic/claude-opus-4.5",
                        "gpt": "openai/gpt-5-pro",
                        "kimi": "moonshotai/kimi-k2.5",
                        "minimax": "minimax/minimax-m2.5",
                        "qwen": "qwen/qwen3.5-plus-02-15"}
        self.client = OpenRouterAPIClient(model_name[client_type])
        with open(schema_path, "r") as f:
            self.schema = json.load(f)

    # ── reading ──────────────────────────────────────────────────────────────

    @staticmethod
    def read_report(report_path: str) -> str:
        """
        Extract the text of a report (.pdf, .txt or .md). Every pdf page starts with a [Page N] marker,
        so that the LLM can state where it found each component.
        """
        ext = os.path.splitext(report_path)[1].lower()
        if ext == ".pdf":
            reader = PdfReader(report_path)
            pages = [f"[Page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, start=1)]
            text = "\n\n".join(pages)
        elif ext in (".txt", ".md"):
            with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        else:
            raise ValueError(f"Unsupported report format '{ext}', use .pdf, .txt or .md")

        if not re.sub(r"\[Page \d+\]", "", text).strip():
            raise ValueError(f"No text found in {report_path}. Scanned reports need OCR first.")
        return text

    # ── LLM ──────────────────────────────────────────────────────────────────

    @staticmethod
    def build_prompt(report_text: str) -> str:
        return (
            "You are a building energy retrofit engineer reviewing a property condition assessment (PCA) report.\n"
            "Extract the information in the given schema.\n\n"
            "Rules:\n"
            "- Use only what the report states. If something is not stated, use null (or 'Not stated' for the condition and timing).\n"
            "- Do not estimate ages or costs that the report does not give.\n"
            "- The only value you may estimate is the remaining useful life. If the report states it, copy it and set from_report to true. "
            "Otherwise estimate it from the install year or age, the expected useful life and the condition, and set from_report to false. "
            "If it cannot be estimated, use null with from_report false.\n"
            "- Create one component entry for every building component or system that the report assesses.\n"
            "- If a component is listed in a table of immediate repairs or in the capital reserve schedule, take its action, timing and cost from there.\n"
            "- Costs are plain numbers without currency symbols or thousands separators.\n"
            "- Areas are in m2 (1 ft2 = 0.0929 m2). Keep other units as written.\n"
            "- Mark a component as energy related if it affects heating, cooling, ventilation, lighting or envelope performance.\n"
            "- Give every component an id (C1, C2, ...). Create one event (E1, E2, ...) for every recommended repair, replacement, "
            "upgrade, study or scheduled maintenance, including each line of the immediate repairs table and the capital reserve schedule. "
            "An event lists the ids of the components it applies to.\n"
            "- Work split into phases is one event per phase. Recurring work is one event with the interval in the timing.\n"
            "- Do not calculate quantities, unit costs or percentages that the report does not give. "
            "If the report gives only a total, leave the unit cost null.\n\n"
            f"PCA report:\n{report_text}"
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences that some LLMs wrap around JSON output."""
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text.strip())
        return text.strip()

    @staticmethod
    def save_result(result: dict, report_path: str, output_root: str = OUTPUT_ROOT) -> str:
        """
        Save the result as <output_root>/<report id>_<NN>/summary.json, where the report id is the report
        file name without extension and NN is a serial number (01, 02, ...) that increases with every run.
        Returns the path of the json file.
        """
        report_id = os.path.splitext(os.path.basename(report_path))[0]
        os.makedirs(output_root, exist_ok=True)
        pattern = re.compile(rf"^{re.escape(report_id)}_(\d+)$")
        used = [int(m.group(1)) for d in os.listdir(output_root) if (m := pattern.match(d))]
        run_dir = os.path.join(output_root, f"{report_id}_{max(used, default=0) + 1:02d}")
        os.makedirs(run_dir)
        json_path = os.path.join(run_dir, "summary.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        return json_path

    def analyze(self, report_path: str, save: bool = True, output_root: str = OUTPUT_ROOT) -> dict:
        """
        Read one report, ask the LLM and return the structured result.
        If save is True, the result is also stored in <output_root>/<report id>_<NN>/summary.json
        """
        report_text = self.read_report(report_path)
        response = self.client.structured_output(self.build_prompt(report_text), self.schema)
        try:
            result = json.loads(self._strip_fences(response))
        except json.JSONDecodeError as exc:
            raise ValueError(f"The LLM did not return valid JSON for {report_path}: {response[:300]}") from exc

        if save:
            print(f"Saved {self.save_result(result, report_path, output_root)}")
        return result

    def analyze_folder(self, folder: str, save: bool = True, output_root: str = OUTPUT_ROOT) -> dict:
        """Analyze every .pdf, .txt and .md report in a folder. Returns {file name: result}"""
        results = {}
        for file_name in sorted(os.listdir(folder)):
            if os.path.splitext(file_name)[1].lower() in (".pdf", ".txt", ".md"):
                print(f"Analyzing {file_name}")
                results[file_name] = self.analyze(os.path.join(folder, file_name), save, output_root)
        return results



