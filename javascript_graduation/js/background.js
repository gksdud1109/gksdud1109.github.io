const backgrounds = ["0.jpg", "1.jpg", "2.jpg", "3.jpg", "4.jpg"];

const randomJpg = backgrounds[Math.floor(Math.random() * backgrounds.length)];
console.log(randomJpg);
//const bgImage = document.createElement("img");

//bgImage.src = `img/${randomJpg}`;

//document.body.appendChild(bgImage);

document.body.style = `background-image: url("img/${randomJpg}");`;