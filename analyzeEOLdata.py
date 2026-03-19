import csv
import math
import datetime
import time
import requests
from typing import List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from functools import wraps


# --- Decorators ---
def retry_on_exception(retries: int = 3, delay: int = 2):
    """Decorator to retry a function if it raises an exception."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        print(f"Failed after {retries} attempts: {e}")
                        raise
                    time.sleep(delay)

        return wrapper

    return decorator


# --- Pydantic Models ---
class CellData(BaseModel):
    partID: str = Field(alias='cell_batch___cell_part___main_id', default="")
    cap: float = Field(alias='___cycle_n1_capacity__ah_', default=math.nan)
    energy: float = Field(alias='___cycle_n1_energy__wh_', default=math.nan)
    GED: float = Field(alias='___cycle_n1_ged__wh_kg_', default=math.nan)
    GED_prev: float = Field(alias='latest_cap_check__n1_ged__wh_kg_', default=math.nan)
    OCVafterSoak: float = Field(alias='s40_ocv_', default=math.nan)
    ACIR: float = Field(alias='s80_1d_ir__mohm_', default=math.nan)
    cycles: float = Field(alias='___cap_check_cycles__corrected', default=math.nan)
    n_capCheckPending: float = Field(alias='cap_check_tests_awaiting_start', default=math.nan)
    checkPrevRetest: str = Field(alias='retest_result_screening', default="")
    n_OCVresetPending: float = Field(alias='ocv_reset_tests_awaiting_start', default=math.nan)
    w: float = Field(alias='s70_final_meas_weight__g_', default=math.nan)
    t: float = Field(alias='s70_final_meas_thickness__mm_', default=math.nan)
    OCVdropRate: float = Field(alias='x80_7d_ocv_drop_rate', default=math.nan)
    IR_USL: float = Field(alias='cell_batch___cell_part___cell_spec___s70_1_day_ir_usl__mohm_', default=math.nan)
    GED_LSL: float = Field(alias='cell_batch___cell_part___cell_spec___n1_ged_lsl__wh_kg_', default=math.nan)
    thickness_USL: float = Field(alias='cell_thickness_usl__mm_', default=math.nan)
    thickness_LSL: float = Field(alias='cell_thickness_lsl__mm_', default=math.nan)
    OCVdroprate_USL: float = Field(alias='cell_batch___cell_part___cell_spec___ocv_drop_usl__mv_day_', default=math.nan)
    OCVdroprate_LSL: float = Field(alias='cell_batch___cell_part___cell_spec___ocv_drop_lsl__mv_day_', default=math.nan)

    @field_validator('*', mode='before')
    def parse_floats(cls, v):
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return v if v else math.nan
        return v


# --- API Client ---
class QuickBaseClient:
    """Object-oriented wrapper for QuickBase API using requests."""

    def __init__(self, url: str, database: str, user_token: str):
        self.url = url.rstrip('/')
        self.database = database
        self.headers = {
            'QB-Realm-Hostname': self.url.replace('https://', '').split('/')[0],
            'Authorization': f'QB-USER-TOKEN {user_token}',
            'Content-Type': 'application/json'
        }
        self.api_base = "https://api.quickbase.com/v1/records"

    @retry_on_exception(retries=3)
    def doquery(self, query: str) -> Dict[str, Any]:
        """Mock querying JSON API returning parsed pyqb-like dictionary."""
        payload = {"from": self.database, "where": query}
        response = requests.post(f"{self.api_base}/query", headers=self.headers, json=payload)
        response.raise_for_status()
        # Note: A real implementation would parse QB's specific JSON response to a flat dict
        return response.json()

    @retry_on_exception(retries=3)
    def editrecord(self, rid: str, fields: Dict[str, str]) -> Dict:
        """Mock editing record via JSON API."""
        formatted_fields = {k: {"value": v} for k, v in fields.items()}
        payload = {"to": self.database, "data": [{"3": {"value": rid}, **formatted_fields}]}
        response = requests.post(self.api_base, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    @retry_on_exception(retries=3)
    def addrecord(self, fields: Dict[str, str]) -> Dict:
        """Mock adding record via JSON API."""
        formatted_fields = {k: {"value": v} for k, v in fields.items()}
        payload = {"to": self.database, "data": [formatted_fields]}
        response = requests.post(self.api_base, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


# --- Main Application Logic ---
class BatteryInspector:
    # Constants
    TS_CAP_CHECK = {
        "CL65_0": "3043", "CL65": "3126", "CL75": "3283",
        "CL76": "3283", "CL77": "3283", "SA102": "3028"
    }
    TS_RESET_OCV = {
        "CL65": "2682", "CL75": "2691", "CL76": "2691",
        "CL77": "2691", "SA102": "3312"
    }
    CYCLE_N1 = {
        "CL65": "2", "CL75": "1", "CL76": "1", "CL77": "1", "SA102": "1"
    }

    def __init__(self, token: str):
        self.qb_cells = QuickBaseClient(
            url='https://company.quickbase.com/', database='cell_table_id', user_token=token)
        self.qb_tests = QuickBaseClient(
            url='https://company.quickbase.com/', database='test_table_id', user_token=token)

        self.list_capCheck_cells: List[str] = []
        self.list_capCheck_partIDs: List[str] = []
        self.list_resetOCV_cells: List[str] = []
        self.list_resetOCV_partIDs: List[str] = []
        self.list_removeCapCheck_cells: List[str] = []
        self.list_removeCapCheck_partIDs: List[str] = []

    def get_csv_cells(self) -> List[str]:
        """Prompts for CSV and returns cell IDs using Context Manager and List Comprehension."""
        while True:
            filename = input('Input csv file name with the list of FI cells: ')
            filepath = f'{filename}.csv'
            try:
                with open(filepath, mode='r') as csvfile:
                    reader = csv.reader(csvfile)
                    next(reader)  # Skip header
                    print('Csv list file found to process')
                    return [row[0] for row in reader if row]
            except OSError:
                print('Oops! Cannot find file. Try again...')

    def resetOCV(self, cellID: str, partID: str, data: CellData):
        if (data.n_capCheckPending >= 1 and data.cycles >= 8) or data.n_capCheckPending == 0:
            if not self.list_capCheck_cells or self.list_capCheck_cells[-1] != cellID:
                self.qb_cells.editrecord(rid=cellID, fields={"622": "yes"})
                if data.n_OCVresetPending == 0:
                    self.list_resetOCV_cells.append(cellID)
                    self.list_resetOCV_partIDs.append(partID)

    def rerunCapCheck(self, cellID: str, partID: str, data: CellData, GED_LSL_retest: float, maxCycles: float):
        if data.n_capCheckPending >= 1:
            if data.cycles < maxCycles and (math.isnan(data.GED_prev) or (
                    data.GED_prev >= GED_LSL_retest and "decrease" not in data.checkPrevRetest and "same" not in data.checkPrevRetest)):
                self.qb_cells.editrecord(rid=cellID, fields={"619": "yes"})
            else:
                self.list_removeCapCheck_cells.append(cellID)
                self.list_removeCapCheck_partIDs.append(partID)
        else:
            if data.cycles < maxCycles and (math.isnan(data.GED_prev) or (
                    data.GED_prev >= GED_LSL_retest and "decrease" not in data.checkPrevRetest and "same" not in data.checkPrevRetest)):
                if not math.isnan(data.OCVdropRate) and data.OCVdropRate <= 2 * data.OCVdroprate_USL:
                    self.qb_cells.editrecord(rid=cellID, fields={"619": "yes", "29": "Retest"})
                    if data.n_capCheckPending == 0 and cellID not in self.list_capCheck_cells:
                        self.list_capCheck_cells.append(cellID)
                        self.list_capCheck_partIDs.append(partID)

    def process_cells(self, cells: List[str]):
        """Main processing loop for each cell ID."""
        for cellID in cells:
            print(f'Processing cell ID#{cellID}')
            try:
                qb_data = self.qb_cells.doquery(query=f'{{3.EX."{cellID}"}}')
                record_dict = qb_data.get('record', {})

                # Using Pydantic for validation and type enforcement
                data = CellData(**record_dict)
            except Exception as e:
                print(f"Error fetching or parsing data for {cellID}: {e}")
                continue

            # Clear old check marks
            self.qb_cells.editrecord(rid=cellID, fields={
                "619": "no", "620": "no", "621": "no",
                "622": "no", "623": "no", "625": "no"
            })

            # Check GED Logic
            GED_LSL_retest = data.GED_LSL
            maxCapCheckCycles = 5

            if data.partID == "CL0076":
                data.GED_LSL = 441
                GED_LSL_retest = 438
            elif data.partID in ["RD0076", "CL0075", "RD0075", "RD0077", "RD0102", "CL0102"]:
                GED_LSL_retest = data.GED_LSL * 0.995
            elif data.partID in ["CL0065", "RD0065"]:
                GED_LSL_retest = data.GED_LSL - 30
                maxCapCheckCycles = 8

            if not math.isnan(data.GED_LSL) and not math.isnan(data.GED):
                if data.GED < data.GED_LSL:
                    self.rerunCapCheck(cellID, data.partID, data, GED_LSL_retest, maxCapCheckCycles)
                elif data.n_capCheckPending > 0:
                    self.list_removeCapCheck_cells.append(cellID)
                    self.list_removeCapCheck_partIDs.append(data.partID)
            else:
                if math.isnan(data.w):
                    self.qb_cells.editrecord(rid=cellID, fields={"623": "yes"})
                elif data.GED_prev > data.GED_LSL:
                    if data.n_capCheckPending > 0:
                        self.list_removeCapCheck_cells.append(cellID)
                        self.list_removeCapCheck_partIDs.append(data.partID)
                else:
                    if data.n_capCheckPending == 0:
                        self.qb_cells.editrecord(rid=cellID, fields={"625": "yes"})
                    else:
                        self.rerunCapCheck(cellID, data.partID, data, GED_LSL_retest, maxCapCheckCycles)

            # OCV drop rate logic
            if math.isnan(data.OCVdropRate):
                self.qb_cells.editrecord(rid=cellID, fields={"621": "yes", "21": "", "22": "", "109": ""})
                self.resetOCV(cellID, data.partID, data)
            elif data.OCVdropRate < data.OCVdroprate_LSL or (
                    data.OCVdroprate_USL < data.OCVdropRate <= 2 * data.OCVdroprate_USL):
                self.qb_cells.editrecord(rid=cellID, fields={"621": "yes", "21": "", "22": "", "108": "", "109": ""})
            elif data.OCVdropRate > 2 * data.OCVdroprate_USL:
                self.qb_cells.editrecord(rid=cellID, fields={"619": "no", "625": "yes"})

            # ACIR Logic
            if not math.isnan(data.IR_USL):
                IR_USL_remeas = data.IR_USL + 40 if data.partID in ["RD0065", "CL0065"] else data.IR_USL + 10
                if math.isnan(data.ACIR) or (data.IR_USL < data.ACIR <= IR_USL_remeas):
                    self.qb_cells.editrecord(rid=cellID, fields={"620": "yes"})

            # Thickness Logic
            if data.partID in ["RD0065", "CL0065"]:
                if math.isnan(data.t):
                    self.qb_cells.editrecord(rid=cellID, fields={"623": "yes"})
                elif data.t < data.thickness_LSL:
                    self.qb_cells.editrecord(rid=cellID, fields={"623": "yes", "19": ""})
                elif data.t > data.thickness_USL:
                    self.qb_cells.editrecord(rid=cellID, fields={"623": "yes", "19": ""})
                    print('  Thickness too high, check GED and adding retest')
                    self.rerunCapCheck(cellID, data.partID, data, GED_LSL_retest, maxCapCheckCycles)

    def perform_qb_imports(self):
        """Map part IDs to test configurations and perform API calls."""
        print('\nCells to retest:', self.list_capCheck_cells)
        for cellID, partID in zip(self.list_capCheck_cells, self.list_capCheck_partIDs):
            test_type = partID[-2:] if partID[-2:] in ["75", "76", "77", "65"] else "102"
            key = f"CL{test_type}" if test_type != "102" else "SA102"
            try:
                self.qb_tests.addrecord(fields={
                    "6": cellID,
                    "9": self.TS_CAP_CHECK.get(key, ""),
                    "59": self.CYCLE_N1.get(key, "")
                })
            except Exception as e:
                print(f"Failed to add retest for {cellID}: {e}")

        print('Cells to reset OCV and remeasure OCVs:', self.list_resetOCV_cells)
        for cellID, partID in zip(self.list_resetOCV_cells, self.list_resetOCV_partIDs):
            test_type = partID[-2:] if partID[-2:] in ["75", "76", "77", "65"] else "102"
            key = f"CL{test_type}" if test_type != "102" else "SA102"
            try:
                self.qb_tests.addrecord(fields={
                    "6": cellID,
                    "9": self.TS_RESET_OCV.get(key, "")
                })
            except Exception as e:
                print(f"Failed to add OCV reset for {cellID}: {e}")

    def write_logs(self):
        """Context Manager for writing logs."""
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        logfile = f"log_{timestamp_str}.csv"

        try:
            with open(logfile, "w", newline="") as output_file:
                writer = csv.writer(output_file, delimiter=',')
                writer.writerow(["Cells to retest:"])
                for cell in self.list_capCheck_cells:
                    writer.writerow([cell])
                writer.writerow(["Cells to reset OCV:"])
                for cell in self.list_resetOCV_cells:
                    writer.writerow([cell])
            print(f"Log written to {logfile}")
        except IOError as e:
            print(f"Error writing log file: {e}")


def main():
    token = 'user_token'
    inspector = BatteryInspector(token=token)

    cells_to_process = inspector.get_csv_cells()
    if cells_to_process:
        inspector.process_cells(cells_to_process)
        inspector.perform_qb_imports()
        inspector.write_logs()


if __name__ == "__main__":
    main()