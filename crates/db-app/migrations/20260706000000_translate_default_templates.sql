-- Localize the seeded default templates to Russian (titles, descriptions,
-- categories, target roles and section titles/descriptions). Applied as a new
-- migration so it also updates DBs that were already seeded in English.

UPDATE templates SET
  title = 'Заседание совета директоров',
  description = 'Для заседаний совета директоров и вопросов управления',
  category = 'Руководство',
  targets_json = '["Основатель","CEO","Член совета директоров"]',
  sections_json = '[{"title":"Результаты компании","description":"Финансовые и операционные обновления"},{"title":"Стратегические инициативы","description":"Прогресс по ключевым приоритетам"},{"title":"Финансовый обзор","description":"Бюджет, запас средств и финансовое здоровье"},{"title":"Решения совета","description":"Резолюции и вопросы управления"},{"title":"Риски и комплаенс","description":"Управление рисками и обновления по комплаенсу"},{"title":"Дальнейшие шаги","description":"Задачи и последующие действия"}]'
WHERE id = 'default-board-meeting';

UPDATE templates SET
  title = 'Мозговой штурм',
  description = 'Для креативного мозгового штурма и генерации идей',
  category = 'Продукт',
  targets_json = '["Продакт-менеджер","Дизайнер","Маркетинг"]',
  sections_json = '[{"title":"Цель сессии","description":"Какую проблему или возможность мы исследуем?"},{"title":"Сгенерированные идеи","description":"Все идеи, зафиксированные во время штурма"},{"title":"Перспективные концепции","description":"Идеи, которые стоит проработать глубже"},{"title":"Критерии оценки","description":"Как мы будем оценивать идеи"},{"title":"Дальнейшие шаги","description":"Задачи для продвижения вперёд"}]'
WHERE id = 'default-brainstorming-session';

UPDATE templates SET
  title = 'Стартовая встреча с клиентом',
  description = 'Для запуска работы с новым клиентом и согласования ожиданий',
  category = 'Работа с клиентами',
  targets_json = '["Менеджер по работе с клиентами","Аккаунт-менеджер","Руководитель внедрения"]',
  sections_json = '[{"title":"Обзор проекта","description":"Объём, цели и результаты"},{"title":"Знакомство команды","description":"Роли и обязанности"},{"title":"Сроки и вехи","description":"График проекта и ключевые даты"},{"title":"План коммуникаций","description":"Частота встреч и обновлений"},{"title":"Критерии успеха","description":"Как измеряем успех проекта"},{"title":"Дальнейшие шаги","description":"Ближайшие задачи"}]'
WHERE id = 'default-client-kickoff';

UPDATE templates SET
  title = 'Интервью с клиентом (Customer Discovery)',
  description = 'Для интервью по исследованию клиентов и пользователей',
  category = 'Продукт',
  targets_json = '["Продакт-менеджер","UX-исследователь","Основатель"]',
  sections_json = '[{"title":"Контекст","description":"Контекст и предыстория клиента"},{"title":"Текущий процесс","description":"Как они сейчас решают проблему"},{"title":"Боли","description":"Сложности и разочарования"},{"title":"Потребности и цели","description":"Чего они пытаются достичь"},{"title":"Отзыв о решении","description":"Реакция на предложенное решение"},{"title":"Ключевые инсайты","description":"Главные выводы и наблюдения"}]'
WHERE id = 'default-customer-discovery';

UPDATE templates SET
  title = 'Ежедневный стендап',
  description = 'Для быстрых ежедневных синков: прогресс и блокеры',
  category = 'Разработка',
  targets_json = '["Разработчик","Инженерный менеджер","Скрам-мастер"]',
  sections_json = '[{"title":"Сделано вчера","description":"Что вы завершили вчера?"},{"title":"План на сегодня","description":"Над чем работаете сегодня?"},{"title":"Блокеры","description":"Есть ли препятствия или нужна помощь?"},{"title":"Новости команды","description":"Важные объявления или информация"}]'
WHERE id = 'default-daily-standup';

UPDATE templates SET
  title = 'Брифинг для руководства',
  description = 'Для фиксации стратегических обсуждений и решений на высоком уровне',
  category = 'Руководство',
  targets_json = '["Руководитель","CEO","VP"]',
  sections_json = '[{"title":"Стратегический обзор","description":"Контекст и цели верхнего уровня"},{"title":"Ключевые метрики","description":"Показатели эффективности и тренды"},{"title":"Основные решения","description":"Стратегические решения и их обоснование"},{"title":"Распределение ресурсов","description":"Бюджет и обязательства по ресурсам"},{"title":"Риски и возможности","description":"Стратегические риски и возможности роста"},{"title":"Задачи","description":"Последующие действия уровня руководства"}]'
WHERE id = 'default-executive-briefing';

UPDATE templates SET
  title = 'Разбор инцидента (Postmortem)',
  description = 'Для безобвинительного разбора после инцидентов и сбоев',
  category = 'Разработка',
  targets_json = '["Платформенный инженер","SRE","DevOps-инженер"]',
  sections_json = '[{"title":"Краткое описание инцидента","description":"Что произошло и когда"},{"title":"Хронология событий","description":"Последовательность событий по времени"},{"title":"Анализ первопричины","description":"Что вызвало инцидент"},{"title":"Оценка влияния","description":"Влияние на пользователей и бизнес"},{"title":"Реагирование и устранение","description":"Как инцидент был устранён"},{"title":"Извлечённые уроки","description":"Ключевые выводы и наблюдения"},{"title":"Задачи","description":"Превентивные меры и улучшения"}]'
WHERE id = 'default-incident-postmortem';

UPDATE templates SET
  title = 'Питч для инвесторов',
  description = 'Для презентаций инвесторам и венчурным фондам',
  category = 'Привлечение инвестиций',
  targets_json = '["Основатель","CEO","Финансовый директор"]',
  sections_json = '[{"title":"Контекст встречи","description":"Об инвесторе и цель встречи"},{"title":"Суть питча","description":"Ключевые представленные тезисы"},{"title":"Заданные вопросы","description":"Вопросы и опасения инвестора"},{"title":"Полученная обратная связь","description":"Реакция и отзывы инвестора"},{"title":"Интерес к инвестициям","description":"Уровень интереса и дальнейшие шаги"},{"title":"Последующие действия","description":"Запрошенная информация и задачи"}]'
WHERE id = 'default-investor-pitch';

UPDATE templates SET
  title = 'Конспект лекции',
  description = 'Для фиксации и систематизации материала лекции',
  category = 'Образование',
  targets_json = '["Студент","Аспирант","Исследователь"]',
  sections_json = '[{"title":"Информация о лекции","description":"Курс, дата и тема"},{"title":"Ключевые концепции","description":"Основные идеи и теории"},{"title":"Важные определения","description":"Термины и определения для запоминания"},{"title":"Примеры и применение","description":"Примеры и практическое применение"},{"title":"Вопросы и уточнения","description":"Что нужно уточнить позже"},{"title":"Задачи","description":"Домашнее задание и дальнейшие шаги"}]'
WHERE id = 'default-lecture-notes';

UPDATE templates SET
  title = 'Встреча один на один (1:1)',
  description = 'Для структурированных встреч один на один с сотрудниками',
  category = 'Менеджмент',
  targets_json = '["Менеджер","Инженерный менеджер","Тимлид"]',
  sections_json = '[{"title":"Обновления","description":"Что произошло с прошлого раза?"},{"title":"Успехи и сложности","description":"Отметить успехи и обсудить препятствия"},{"title":"Цели и прогресс","description":"Обзор текущих целей и прогресса"},{"title":"Обратная связь","description":"Двусторонний обмен обратной связью"},{"title":"Задачи","description":"Дальнейшие шаги и договорённости"}]'
WHERE id = 'default-one-on-one-meeting';

UPDATE templates SET
  title = 'Оценка эффективности',
  description = 'Для оценки эффективности сотрудника и обсуждения развития карьеры',
  category = 'Менеджмент',
  targets_json = '["Менеджер","Инженерный менеджер","HR"]',
  sections_json = '[{"title":"Итоги периода","description":"Обзор оцениваемого периода"},{"title":"Ключевые достижения","description":"Главные достижения и вклад"},{"title":"Сильные стороны","description":"Навыки и поведение, которые стоит продолжать"},{"title":"Зоны развития","description":"Возможности роста и улучшения"},{"title":"Карьерные цели","description":"Карьерные устремления и путь развития"},{"title":"План действий","description":"Цели развития и дальнейшие шаги"}]'
WHERE id = 'default-performance-review';

UPDATE templates SET
  title = 'Обзор дорожной карты продукта',
  description = 'Для обзора и согласования приоритетов дорожной карты продукта',
  category = 'Продукт',
  targets_json = '["Продакт-менеджер","Инженерный менеджер","Руководитель"]',
  sections_json = '[{"title":"Текущий статус","description":"Прогресс по текущим инициативам"},{"title":"Предстоящие фичи","description":"Приоритеты и сроки следующего квартала"},{"title":"Обратная связь клиентов","description":"Ключевые инсайты от пользователей и клиентов"},{"title":"Метрики успеха","description":"KPI и подход к измерению"},{"title":"Распределение ресурсов","description":"Назначения команды и ёмкость"},{"title":"Принятые решения","description":"Ключевые решения и компромиссы"}]'
WHERE id = 'default-product-roadmap-review';

UPDATE templates SET
  title = 'Старт проекта',
  description = 'Для запуска новых проектов с чёткими целями и согласованием',
  category = 'Продукт',
  targets_json = '["Продакт-менеджер","Инженерный менеджер","Дизайнер"]',
  sections_json = '[{"title":"Обзор проекта","description":""},{"title":"Цели и метрики успеха","description":"Определить, как выглядит успех"},{"title":"Стейкхолдеры и роли","description":""},{"title":"Сроки и вехи","description":""},{"title":"Риски и зависимости","description":""},{"title":"Дальнейшие шаги","description":""}]'
WHERE id = 'default-project-kickoff';

UPDATE templates SET
  title = 'Ознакомительный звонок по продажам',
  description = 'Для квалификации лидов и понимания потребностей клиента',
  category = 'Продажи',
  targets_json = '["Менеджер по продажам","Торговый представитель","BDR"]',
  sections_json = '[{"title":"О компании","description":"Информация о потенциальном клиенте"},{"title":"Текущая ситуация","description":"Как они работают сегодня"},{"title":"Сложности и боли","description":"Проблемы, которые они пытаются решить"},{"title":"Цели и критерии успеха","description":"Как выглядит успех"},{"title":"Бюджет и сроки","description":"Финансовые и временные ограничения"},{"title":"Дальнейшие шаги","description":"Последующие действия и сроки"}]'
WHERE id = 'default-sales-discovery-call';

UPDATE templates SET
  title = 'Планирование спринта',
  description = 'Для планирования спринтов разработки и постановки целей команды',
  category = 'Разработка',
  targets_json = '["Инженерный менеджер","Продакт-менеджер","Техлид"]',
  sections_json = '[{"title":"Цель спринта","description":"Какова главная цель этого спринта?"},{"title":"Бэклог спринта","description":"Истории и задачи, взятые в спринт"},{"title":"Ёмкость и доступность","description":"Доступность команды и оценка ёмкости"},{"title":"Зависимости и риски","description":"Внешние зависимости и возможные риски"},{"title":"Критерии готовности (DoD)","description":"Критерии приёмки и стандарты завершения"}]'
WHERE id = 'default-sprint-planning';

UPDATE templates SET
  title = 'Ретроспектива спринта',
  description = 'Для рефлексии по спринтам и постоянного улучшения процессов и командной работы',
  category = 'Разработка',
  targets_json = '["Инженерный менеджер","Скрам-мастер","Техлид"]',
  sections_json = '[{"title":"Что прошло хорошо","description":"Отметить успехи и позитивные результаты"},{"title":"Что прошло плохо","description":"Выявить сложности и проблемы"},{"title":"Чему научились","description":"Ключевые инсайты и выводы"},{"title":"Задачи","description":"Конкретные шаги для улучшения"}]'
WHERE id = 'default-sprint-retrospective';

UPDATE templates SET
  title = 'Обзор технического дизайна',
  description = 'Для обзора технических решений и архитектурных выборов',
  category = 'Разработка',
  targets_json = '["Разработчик","Техлид","Платформенный инженер"]',
  sections_json = '[{"title":"Постановка задачи","description":"Какую проблему мы решаем?"},{"title":"Предлагаемое решение","description":"Технический подход и архитектура"},{"title":"Рассмотренные альтернативы","description":"Другие варианты и компромиссы"},{"title":"План реализации","description":"Разбивка работ и сроки"},{"title":"Стратегия тестирования","description":"Как проверим решение"},{"title":"Риски и меры","description":"Возможные проблемы и планы на случай сбоев"},{"title":"Решения и задачи","description":"Итоги и дальнейшие шаги"}]'
WHERE id = 'default-technical-design-review';
