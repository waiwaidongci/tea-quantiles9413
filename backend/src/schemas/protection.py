from pydantic import BaseModel,Field
class ProtectionPolicyInput(BaseModel):
    field:str|None=None
    bins:list[float]|None=None
    total_epsilon:float|None=None
class ProtectionReleaseInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    epsilon:float|None=None
