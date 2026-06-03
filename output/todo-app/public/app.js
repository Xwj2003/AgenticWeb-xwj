document.addEventListener('DOMContentLoaded', () => {
    loadTodos();
    document.getElementById('toggle-dark-mode').addEventListener('click', toggleDarkMode);
    document.getElementById('add-task-form').addEventListener('submit', addTask);
});

async function loadTodos() {
    try {
        const response = await fetch('/api/todos');
        if (!response.ok) {
            throw new Error('Failed to fetch todos');
        }
        const todos = await response.json();
        renderTodos(todos);
    } catch (error) {
        console.error(error);
        alert('Error loading todos. Please try again later.');
    }
}

function renderTodos(todos) {
    const todoList = document.getElementById('todo-list');
    todoList.innerHTML = '';
    todos.forEach(todo => {
        const li = document.createElement('li');
        li.textContent = todo.title;
        if (todo.completed) {
            li.style.textDecoration = 'line-through';
        }
        li.appendChild(createDeleteButton(todo.id));
        li.appendChild(createEditButton(todo.id, todo.title));
        li.appendChild(createCompleteButton(todo.id, todo.completed));
        todoList.appendChild(li);
    });
}

function createDeleteButton(id) {
    const button = document.createElement('button');
    button.textContent = 'Delete';
    button.addEventListener('click', () => deleteTask(id));
    return button;
}

function createEditButton(id, title) {
    const button = document.createElement('button');
    button.textContent = 'Edit';
    button.addEventListener('click', () => editTask(id, title));
    return button;
}

function createCompleteButton(id, completed) {
    const button = document.createElement('button');
    button.textContent = completed ? 'Mark Incomplete' : 'Mark Complete';
    button.addEventListener('click', () => toggleComplete(id, completed));
    return button;
}

async function addTask(event) {
    event.preventDefault();
    const title = document.getElementById('task-title').value.trim();
    if (title === '') {
        alert('Please enter a task title.');
        return;
    }
    try {
        const response = await fetch('/api/todos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ title })
        });
        if (!response.ok) {
            throw new Error('Failed to add task');
        }
        const todo = await response.json();
        renderTodos([todo]);
        document.getElementById('task-title').value = '';
    } catch (error) {
        console.error(error);
        alert('Error adding task. Please try again later.');
    }
}

async function deleteTask(id) {
    try {
        const response = await fetch(`/api/todos/${id}`, { method: 'DELETE' });
        if (!response.ok) {
            throw new Error('Failed to delete task');
        }
        loadTodos();
    } catch (error) {
        console.error(error);
        alert('Error deleting task. Please try again later.');
    }
}

async function editTask(id, title) {
    const newTitle = prompt('Enter the new task title:', title);
    if (newTitle === null || newTitle.trim() === '') {
        return;
    }
    try {
        const response = await fetch(`/api/todos/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ title: newTitle })
        });
        if (!response.ok) {
            throw new Error('Failed to update task');
        }
        loadTodos();
    } catch (error) {
        console.error(error);
        alert('Error updating task. Please try again later.');
    }
}

async function toggleComplete(id, completed) {
    const newCompleted = !completed;
    try {
        const response = await fetch(`/api/todos/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ completed: newCompleted })
        });
        if (!response.ok) {
            throw new Error('Failed to update task');
        }
        loadTodos();
    } catch (error) {
        console.error(error);
        alert('Error updating task. Please try again later.');
    }
}

function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
}