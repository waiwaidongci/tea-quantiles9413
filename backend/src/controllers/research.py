from src.services import studies,runs
# Controllers keep endpoint contracts separate from persistence and calculation.
def overview(db,user=None): return {'studies':studies.list_studies(db,user),'runs':runs.list_runs(db,user)}
def create_study(db,data,user): return studies.create(db,data,user)
def list_rows(db,id,user=None): return studies.observations(db,id,user)
def save_row(db,id,data,user,row_id=None): return studies.save_observation(db,id,data,user,row_id)
def create_run(db,data,user): return runs.create(db,data,user)
def review_run(db,id,data,user): return runs.approve(db,id,data,user)
