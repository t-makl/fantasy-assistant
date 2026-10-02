/* Pure board rules shared by the UI and regression tests. */
const BoardUtils = (() => {
  const normalize = x => String(x ?? '').trim().toLowerCase();
  const playerTags = research => String(research.tags || '').split(',').map(normalize).filter(Boolean);
  function uniqueTags(value) {
    const seen=new Set();
    return (Array.isArray(value)?value:String(value||'').split(',')).map(t=>String(t).trim()).filter(t=>{const key=normalize(t);if(!key||seen.has(key))return false;seen.add(key);return true;});
  }
  function matchesFilters(player, research, purchase, filters, myTeam) {
    const f=filters, pt=playerTags(research), exclusions=f.excluded || {};
    if (f.q && !normalize([player.name,player.team,research.notes,research.tags].join(' ')).includes(normalize(f.q))) return false;
    if (f.position && player.position !== f.position) return false;
    if (f.nbaTeam && player.team !== f.nbaTeam) return false;
    if (f.availability==='available' && purchase) return false;
    if (f.availability==='drafted' && !purchase) return false;
    if (f.availability==='mine' && purchase?.teamId!==myTeam) return false;
    if (f.tier && !(f.tier==='discuss' ? research.discuss : research.tier===f.tier)) return false;
    if (!(f.tags || []).every(t=>pt.includes(normalize(t)))) return false;
    if ((exclusions.tags || []).some(t=>pt.includes(normalize(t)))) return false;
    if ((exclusions.tiers || []).includes(research.tier || '__none')) return false;
    if ((exclusions.positions || []).includes(player.position)) return false;
    return true;
  }
  function compare(a,b,key) {
    if (a==null || b==null || a===b || ['fga','fta','gp'].includes(key)) return 0;
    return (a>b?1:-1)*(key==='tov'?-1:1);
  }
  return {matchesFilters,compare,uniqueTags};
})();
if(typeof module!=='undefined') module.exports=BoardUtils;
