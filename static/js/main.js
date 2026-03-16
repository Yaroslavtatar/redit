/**
 * static/js/main.js
 * ------------------
 * Главный JavaScript-файл фронтенда CREDDIT.
 *
 * На первых этапах здесь почти нет логики — только минимальная
 * инициализация, которая показывает, что файл корректно подключён.
 *
 * Позже мы добавим сюда:
 * - отправку голосов (лайк/дизлайк) через fetch без перезагрузки страницы;
 * - небольшие улучшения UX (подсветка активных элементов, уведомления и т.п.);
 * - возможно, упрощённый клиентский код для работы с формами.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Эта функция выполняется после полной загрузки HTML-документа.
  // Здесь удобно навешивать обработчики событий на элементы страницы.

  console.log("CREDDIT frontend initialized.");

  setupVoting();
});

/**
 * Настройка обработчиков голосования за пост.
 *
 * Общая идея:
 * - На странице детального просмотра поста мы ищем контейнер
 *   `.post-vote-buttons` и вешаем на него обработчик клика.
 * - Когда пользователь нажимает на кнопку лайка/дизлайка, мы:
 *   - читаем значение голоса (1 или -1) из data-атрибута;
 *   - отправляем POST-запрос в JSON-формате на /post/<id>/vote;
 *   - по успешному ответу обновляем текст в элементе с id="post-score".
 *
 * Важно: мы не показываем всплывающие ошибки, чтобы не перегружать
 * интерфейс, но выводим информацию в консоль (для отладки).
 */
function setupVoting() {
  const voteContainer = document.querySelector(".post-vote-buttons");
  if (!voteContainer) {
    // Мы на странице, где нет голосования (например, главная или логин).
    return;
  }

  const postId = voteContainer.getAttribute("data-post-id");
  const scoreElement = document.getElementById("post-score");

  if (!postId || !scoreElement) {
    return;
  }

  voteContainer.addEventListener("click", async (event) => {
    const target = event.target;

    // Нас интересуют только клики по кнопкам с классом btn-vote.
    if (!(target instanceof HTMLElement) || !target.classList.contains("btn-vote")) {
      return;
    }

    const rawValue = target.getAttribute("data-value");
    const value = rawValue === "-1" ? -1 : rawValue === "1" ? 1 : null;

    if (value === null) {
      console.warn("Не удалось определить значение голоса");
      return;
    }

    try {
      const response = await fetch(`/post/${postId}/vote`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ value }),
      });

      if (!response.ok) {
        console.warn("Ошибка при голосовании:", response.status);
        return;
      }

      const data = await response.json();

      if (!data.ok) {
        console.warn("Сервер отклонил голос:", data.error);
        return;
      }

      // Обновляем число в DOM без перезагрузки страницы.
      scoreElement.textContent = String(data.score);
    } catch (error) {
      console.error("Сетевая ошибка при голосовании:", error);
    }
  });
}

