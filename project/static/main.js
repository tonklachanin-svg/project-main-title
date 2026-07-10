function showToast(message, type){
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast toast-show' + (type === 'error' ? ' toast-error' : '');
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(function(){
        toast.className = 'toast';
    }, 3000);
}

document.addEventListener('DOMContentLoaded', function(){
    const pending = sessionStorage.getItem('toastMessage');
    if (pending){
        sessionStorage.removeItem('toastMessage');
        const type = sessionStorage.getItem('toastType') || 'success';
        sessionStorage.removeItem('toastType');
        showToast(pending, type);
    }
});

function saveAndGoToFolder(){
    fetch('/api/case/mark-in-progress', { method: 'POST' })
        .then(function(){ window.location.href = '/folder'; })
        .catch(function(){ window.location.href = '/folder'; });
}

function submitAll() {
    const btn = document.getElementById('btnSubmitAll');
    const oldLabel = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ กำลังส่งข้อมูล...';

    fetch('/api/submit-history', { method: 'POST' })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.status === 'success'){
                sessionStorage.setItem('toastMessage', 'ส่งข้อมูลสำเร็จ');
                sessionStorage.setItem('toastType', 'success');
                window.location.href = '/folder';
                return;
            }
            btn.disabled = false;
            btn.innerHTML = oldLabel;
            showToast(res.message || 'ส่งข้อมูลไม่สำเร็จ', 'error');
        })
        .catch(function(){
            btn.disabled = false;
            btn.innerHTML = oldLabel;
            showToast('เกิดข้อผิดพลาดในการส่งข้อมูล', 'error');
        });
}

function toggleDropdown(btn){
    const menu = btn.nextElementSibling;
    const isOpen = menu.classList.contains('show');
    document.querySelectorAll('.dropdown-menu.show').forEach(function(el){ el.classList.remove('show'); });
    if (!isOpen) menu.classList.add('show');
}

document.addEventListener('click', function(e){
    if (!e.target.closest('.dropdown')){
        document.querySelectorAll('.dropdown-menu.show').forEach(function(el){ el.classList.remove('show'); });
    }
});

function cloneDraft(userId, name){
    if (!confirm('โคลนงานของ "' + name + '" มาทับฉบับร่างของคุณเองหรือไม่?\nข้อมูลที่คุณเคยบันทึกไว้ (ถ้ามี) จะถูกทับด้วยของเพื่อนร่วมงานคนนี้')){
        return;
    }
    fetch('/api/clone-draft', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ source_user_id: userId })
    })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.status !== 'success'){
                showToast(res.message || 'โคลนงานไม่สำเร็จ', 'error');
                return;
            }
            const url = new URL(window.location.href);
            if (url.searchParams.has('user')){
                sessionStorage.setItem('toastMessage', res.message || 'โคลนงานสำเร็จ');
                sessionStorage.setItem('toastType', 'success');
                url.searchParams.delete('user');
                window.location.href = url.pathname + (url.search || '');
            } else {
                showToast(res.message || 'โคลนงานสำเร็จ');
            }
        })
        .catch(function(){ showToast('เกิดข้อผิดพลาดในการโคลนงาน', 'error'); });
}

function cloneFromHistory(entryId, label){
    if (!confirm('โคลนงาน "' + label + '" มาทับฉบับร่างของคุณเองหรือไม่?\nข้อมูลที่คุณเคยบันทึกไว้ (ถ้ามี) จะถูกทับด้วยข้อมูลชุดนี้')){
        return;
    }
    fetch('/api/clone-history/' + entryId, { method: 'POST' })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.status !== 'success'){
                showToast(res.message || 'โคลนงานไม่สำเร็จ', 'error');
                return;
            }
            sessionStorage.setItem('toastMessage', res.message || 'โคลนงานสำเร็จ');
            sessionStorage.setItem('toastType', 'success');
            window.location.href = '/spec-page-1';
        })
        .catch(function(){ showToast('เกิดข้อผิดพลาดในการโคลนงาน', 'error'); });
}

function deleteHistoryEntry(entryId, btn){
    if (!confirm('ลบประวัตินี้ทิ้งถาวรหรือไม่? กู้คืนไม่ได้')){
        return;
    }
    fetch('/api/history/' + entryId + '/delete', { method: 'POST' })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.status !== 'success'){
                showToast(res.message || 'ลบไม่สำเร็จ', 'error');
                return;
            }
            const row = btn.closest('tr');
            if (row) row.remove();
            showToast(res.message || 'ลบประวัติแล้ว');
        })
        .catch(function(){ showToast('เกิดข้อผิดพลาดในการลบประวัติ', 'error'); });
}

function deleteCase(caseId, btn){
    if (!confirm('ลบงานนี้ทิ้งถาวรหรือไม่? กู้คืนไม่ได้')){
        return;
    }
    fetch('/api/folder/' + caseId + '/delete', { method: 'POST' })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.status !== 'success'){
                showToast(res.message || 'ลบไม่สำเร็จ', 'error');
                return;
            }
            const row = btn.closest('tr');
            if (row) row.remove();
            showToast(res.message || 'ลบงานแล้ว');
        })
        .catch(function(){ showToast('เกิดข้อผิดพลาดในการลบงาน', 'error'); });
}

const thaiMap = {
    '0':'๐','1':'๑','2':'๒','3':'๓','4':'๔',
    '5':'๕','6':'๖','7':'๗','8':'๘','9':'๙'
};

const arabicMap = {
    '๐':'0','๑':'1','๒':'2','๓':'3','๔':'4',
    '๕':'5','๖':'6','๗':'7','๘':'8','๙':'9'
};

function convertNode(node, toThai){

    if(node.nodeType === Node.TEXT_NODE){

        node.textContent = node.textContent.replace(
            toThai ? /[0-9]/g : /[๐-๙]/g,
            m => toThai ? thaiMap[m] : arabicMap[m]
        );

        return;
    }

    if(node.nodeType !== Node.ELEMENT_NODE) return;

    if(
        node.tagName === "INPUT" ||
        node.tagName === "TEXTAREA" ||
        node.tagName === "SELECT"
    ){
        return;
    }

    node.childNodes.forEach(child => convertNode(child,toThai));
}

function switchNumber(toThai){

    convertNode(document.body,toThai);

    localStorage.setItem("numberMode",toThai ? "thai" : "arabic");
}

document.addEventListener("DOMContentLoaded",function(){

    if(localStorage.getItem("numberMode")==="thai"){
        switchNumber(true);
    }

});
