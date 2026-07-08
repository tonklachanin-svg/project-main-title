// แจ้งเตือนแบบ toast มุมซ้ายล่าง ใช้ร่วมกันทุกหน้า (เก็บข้อความผ่าน sessionStorage
// เพื่อให้ยังโชว์ได้แม้กดบันทึกแล้วหน้าเปลี่ยน redirect ไปหน้าเอกสารทันที)
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

// เมนู dropdown "อื่นๆ" ในแถบบน — เปิด/ปิดด้วยการคลิก และปิดเองเมื่อคลิกนอกเมนู
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
