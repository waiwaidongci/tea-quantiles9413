import {store} from '../../stores/research.js';
import {esc} from '../../utils/format.js';
import {DOMAIN} from '../../constants/domain.js';
export const studySelect=()=>`<label>${DOMAIN.study_label}<select id="study-select" name="study_id">${store.studies.map(s=>`<option value="${s.id}" ${s.id===store.studyId?'selected':''}>${esc(s.name)} · ${s.row_count===null?'受保护':s.row_count+'条'}</option>`).join('')}</select></label>`;
