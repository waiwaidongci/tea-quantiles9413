from pydantic import BaseModel,Field
class TeaLotInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    source_filename:str=Field(min_length=3,max_length=120)
    description:str=Field(default='',max_length=2000)
StudyInput=TeaLotInput
