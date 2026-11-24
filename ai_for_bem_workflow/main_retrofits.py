import os
import json
from retrofitting.pca_analyzer import PCAAnalyzer

def main():
    pca_directory = r"C:\Users\Hussein Elehwany\Desktop\OneDrive backup\PostDoc\GHGe Playbook\PCA reports"
    analyzer = PCAAnalyzer("gemini")
    # saved automatically to PCA_summaries/<report id>_<NN>/summary.json
    result = analyzer.analyze(os.path.join(pca_directory, "CREtelligent_PCA-ASTM-Debt-Sample-2024-0501.pdf"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()