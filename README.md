# analyze_battery_EOL_data
Automate battery EOL data analysis and update NC disposition on QuickBase

OVERVIEW
This repository contains the End-of-Line (EOL) Inspection Automation script for battery cell manufacturing. The tool streamlines the disposition process by taking a list of scanned cell IDs, querying their test data from QuickBase, and automatically evaluating key performance metrics against specific product tolerances. Based on this analysis, the script automatically updates QuickBase records, queues cells for necessary retests (like cap-checks or OCV resets), and generates local audit logs.

KEY FEATURES
QuickBase Integration: Automatically fetches cell data and pushes disposition updates using the QuickBase REST API.

Intelligent Disposition Logic: Evaluates cells based on Gravimetric Energy Density (GED), Open Circuit Voltage (OCV) drop rates, AC Internal Resistance (ACIR), and physical dimensions (thickness/weight).

Part-Specific Tolerances: Dynamically adjusts Upper/Lower Specification Limits (USL/LSL) and maximum allowed test cycles based on the specific cell Part ID (e.g., CL0065, CL0075, SA102).

Robust Architecture: Built with Object-Oriented Programming (OOP) principles, featuring automated API retry decorators, Context Managers for safe file handling, and Pydantic models for strict data validation.

Automated Test Queueing: Automatically generates new test records in the QuickBase tracking database for cells that require further evaluation.

Local Auditing: Generates timestamped CSV log files detailing exactly which cells were queued for retests or resets.

PREREQUISITES
Python 3.8+

Required Python packages:

Bash
pip install requests pydantic
Usage
Export or scan your list of End-of-Line cell IDs into a CSV file (e.g., batch_001.csv). The cell IDs should be listed in the first column.

Place the CSV file in the same directory as the script.

Run the application:

Bash
python Inspect.py
When prompted, enter the name of your CSV file (without the .csv extension).

The script will process each cell, output its progress to the console, update QuickBase, and generate a log file in the local directory.

SYSTEM WORKFLOW
1. Input: Reads cell IDs from the provided CSV file.
2. Fetch: Queries QuickBase (Database: bqg4mcgag) for the latest EOL metrics for each cell.
3. Validate: Clears previous inspection flags and checks the data:
   - GED Check: Identifies if GED is below spec. If viable, queues a cap-check retest. If max cycles are reached or retest isn't viable, removes pending tests.
   - OCV Drop Rate Check: Evaluates 7-day voltage drop. Flags for OCV reset if data is missing, or escalates if the drop rate is severely out of specification (> 2x USL).
   - ACIR Check: Compares ACIR against the USL (plus part-specific remeasurement buffers) and flags for remeasurement if needed.
   - Thickness/Weight Check: Flags cells with missing weights or out-of-spec thickness for physical remeasurement.
4. Queue: Creates new records in the QuickBase Tests database (bqg4mcgfv) for cells needing Cap-Check Retests or OCV Resets based on their specific Part ID test codes.
5. Log: Writes a timestamped summary CSV (e.g., log_YYYY-MM-DD_HH-MM-SS.csv) listing the cells requiring further action.

CONFIGURATION AND AUTHENICATION
The script relies on a QuickBase User Token for API authentication. Ensure your user token has the appropriate read/write permissions for both the Cells and Tests databases.
