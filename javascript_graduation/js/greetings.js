const loginForm = document.querySelector("#login-form");
const loginInput = document.querySelector("#login-form input");
const greeting = document.querySelector("#greeting");

const CLASS_HIDDEN = "hidden"

function onLogin(event){
    event.preventDefault();
    loginForm.classList.add(CLASS_HIDDEN);
    const name = loginInput.value;
    localStorage.setItem("name", name);
    paintGreetings(name);
}

function paintGreetings(name){
    greeting.innerText = `Hello ${name}`;
    greeting.classList.remove(CLASS_HIDDEN);
    greeting.classList.add("greeting");
}

const savedUsername = localStorage.getItem("name");

if(savedUsername === null) {
    loginForm.classList.remove(CLASS_HIDDEN);
    loginForm.addEventListener("submit", onLogin);
} else {
    paintGreetings(savedUsername);
}
