import {studies,runs,protection} from '../api/research.js';
export const store={studies:[],runs:[],studyId:0,runId:0,rows:[],protection:null,releaseId:0};
export async function load(){[store.studies,store.runs]=await Promise.all([studies.list(),runs.list()]);if(!store.studyId)store.studyId=store.studies[0]?.id||0;}
export async function loadRows(){store.rows=store.studyId?await studies.rows(store.studyId):[];}
export async function loadProtection(){store.protection=store.studyId?await protection.info(store.studyId):null;}
export const releaseBusy=()=>Boolean(store.protection?.releases?.some(r=>r.status==='pending'||r.status==='generating'));
