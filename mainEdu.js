const readline = require('readline');

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

function numberguesser() {
    let randomnumber = Math.floor(Math.random() * 50) + 1; // Генерируем случайное число от 1 до 50
    let Maxpopitki = 10;  // Максимальное количество попыток
    let popitki = 0;  // Счётчик попыток

    function askQuestion() {
        rl.question("Введи число от 1 до 50: ", (usernumber) => {
            usernumber = Number(usernumber);  // Преобразуем строку в число

            if (usernumber === randomnumber) {
                console.log("Ты угадал число " + randomnumber + " с " + (popitki + 1) + " попытки");
                rl.close();  // Закрываем интерфейс readline
            } else {
                popitki++;  // Увеличиваем количество попыток
                if (popitki < Maxpopitki) {
                    console.log("Не угадал, у тебя осталось " + (Maxpopitki - popitki) + " попыток.");
                    askQuestion();  // Повторный запрос
                } else {
                    console.log("Попытки закончились. Было число: " + randomnumber);
                    rl.close();  // Закрываем интерфейс readline
                }
            }
        });
    }

    askQuestion();  // Начинаем задавать вопросы
}

numberguesser();  // Вызов функции

