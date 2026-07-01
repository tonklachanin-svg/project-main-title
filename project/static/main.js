// ===============================
// Login Page
// ===============================

function togglePassword() {

    const input = document.getElementById("password");

    if (!input) return;

    if (input.type === "password") {

        input.type = "text";

    } else {

        input.type = "password";

    }

}
