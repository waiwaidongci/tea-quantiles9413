export async function request(path,options={}) {
 const token=localStorage.getItem('research-token');
 const response=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...options.headers}});
 if(!response.ok){const x=await response.json().catch(()=>({detail:'网络错误，请重试'}));if(response.status===401 && !path.includes('login')){localStorage.clear();location.reload();}throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail));}
 return response.headers.get('content-type')?.includes('text/csv')?response.blob():response.json();
}
export const post=(path,body)=>request(path,{method:'POST',body:JSON.stringify(body)});
