import requests, json, re
from groq import Groq
from types import SimpleNamespace as SN

VK_TOKEN = open("vk_token").read().strip()
GROQ_TOKEN = open("groq_token").read().strip()

class Config:
    MAX_POST_OFFSET = 10
    MAX_POST_COUNT = 10
    ROOT_GROUP = "rusanimefest"
    LLM_MAX_QUERIES = 50
    REDOWNLOAD = False
    MODEL_NAME = "mixtral-8x7b-32768" # May be "llama-3.3-70b-versatile"

groq = Groq(api_key=GROQ_TOKEN)

class APIError(Exception): pass

def vk_request(method, **params):
    try:
        return requests.post(f"https://api.vk.com/method/{method}", params={**params, "v": "5.199"}, headers={"Authorization": f"Bearer {VK_TOKEN}"}).json()["response"]
    except KeyError:
        raise APIError

def ask_llm(s):
    completion = groq.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[
            {
                "role": "user",
                "content": s,
            }
        ],
    )
    return completion.choices[0].message.content.strip()

def pprint(j): # FOR DEBUGGING PURPOSES ONLY
    print(json.dumps(j, indent=4))

def get_posts(group_domain):
    posts = {}
    offset = 0
    while True:
        resp = vk_request("wall.get", domain=group_domain, count=Config.MAX_POST_COUNT, offset=offset)
        if resp["count"] == 0:
            break
        for item in resp["items"]:
            if item["text"]:
                posts[f"https://vk.com/{group_domain}?w=wall{item['from_id']}_{item['id']}"] = item["text"].strip()
        if not resp["next_from"]:
            break
        offset = int(resp["next_from"])
        if offset >= Config.MAX_POST_OFFSET:
            break
    return posts

def download_posts():
    main_group_posts = get_posts(Config.ROOT_GROUP)
    groups_to_ask_about = set()
    for post_text in main_group_posts.values():
        page_re_groups = re.findall(r"vk.com/([\w.]+)|@([\w.]+)|\[([\w.]+)\|[^\]+]\]", post_text)
        for page_re_group in page_re_groups:
            try:
                groups_to_ask_about.add(next(filter(lambda x: x, page_re_group)))
            except StopIteration:
                continue

    print(f"Groups found: {len(groups_to_ask_about)}")

    total_posts = {}
    for i, group in enumerate(groups_to_ask_about, start=1):
        print(f"Processing {group} (group {i}/{len(groups_to_ask_about)})... ", end="", flush=True)
        try:
            posts = get_posts(group)
            total_posts.update(posts)
            print(f"received {len(posts)} posts.")
        except APIError:
            print("error.")
            continue

    json.dump(total_posts, open("posts.json", "w"))

def save_categories(categories):
    f = open("categories.txt", "w", encoding="utf-8")
    for category_name, posts in categories.items():
        f.write(f"===== {category_name} =====\n\n")
        for post in posts:
            f.write(f"***** {post.link} *****\n\n")
            f.write(f"{post.text}\n\n")
        f.write("\n\n")

def main():
    if Config.REDOWNLOAD:
        download_posts()

    posts = json.load(open("posts.json"))

    categories = {name: [] for name in ["Интерактив", "Информационный пост", "Реклама/партнёр", "Наполнитель", "Описание того, что группа делает", "Расписания и адреса"]}
    llm_queries_amount = 0
    for post_link, post_text in posts.items():
        print(f"LLM processes {llm_queries_amount + 1}...")
        try:
            llm_response = ask_llm(
                "Имеющиеся категории: " + ", ".join(categories.keys()) + "\n"
                + "\n"
                + "Вот текст поста группы по проведению мероприятий:\n"
                + "\n"
                + post_text + "\n"
                + "\n"
                + "ОТВЕТЬ ЛИШЬ НАЗВАНИЕМ ОДНОЙ ИЗ КАТЕГОРИЙ, К КОТОРОЙ ОТНОСИТСЯ ПОСТ. ЕСЛИ ПОДХОДЯЩИХ КАТЕГОРИЙ В СПИСКЕ НЕТ, НАПИШИ НАЗВАНИЕ НОВОЙ. НЕ ПИШИ В СВОЁМ ОТВЕТЕ НИЧЕГО КРОМЕ НАЗВАНИЯ КАТЕГОРИИ"
            )
        except KeyboardInterrupt:
            break
        categories.setdefault(llm_response.strip(), []).append(SN(link=post_link, text=post_text))
        llm_queries_amount += 1
        if llm_queries_amount == Config.LLM_MAX_QUERIES:
            break
    save_categories(categories)

main()
