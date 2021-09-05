const toDoForm = document.getElementById("todo-form");
const toDoInput = document.querySelector("#todo-form input");
const toDoList = document.getElementById("todo-list");

const TODOS_KEY="todos";
let toDos = [];

function saveData(){
    localStorage.setItem(TODOS_KEY, JSON.stringify(toDos));
}

function deleteData(event) {
    const li = event.target.parentElement;
    li.remove();
    toDos = toDos.filter((toDo) => toDo.id !== parseInt(li.id));
    saveData();
}

function paintData(todo){
    const list = document.createElement("li");
    list.id = todo.id;
    const span = document.createElement("span");
    const button = document.createElement("button");
    span.innerText = todo.text;
    button.innerText = "X";
    button.addEventListener("click", deleteData);
    list.appendChild(span);
    list.appendChild(button);
    toDoList.appendChild(list);
}

function handleToDoSubmit(event){
    event.preventDefault();
    const newTodo = toDoInput.value;
    toDoInput.value = "";
    const newTodoObj = {
        text: newTodo,
        id: Date.now(),
    };
    toDos.push(newTodoObj);
    paintData(newTodoObj);
    saveData();
}

toDoForm.addEventListener("submit", handleToDoSubmit);

const savedToDos = localStorage.getItem(TODOS_KEY);
if (savedToDos !== null) {
    const parsToDos = JSON.parse(savedToDos);
    toDos = parsToDos;
    parsToDos.forEach(paintData);
}