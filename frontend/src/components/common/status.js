import {STATE_LABELS} from '../../types/enums.js';
export const status=x=>`<span class="status ${x}">${STATE_LABELS[x]||x}</span>`;
