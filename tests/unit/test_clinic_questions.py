"""Off-script questions answered from the directory and the clinic's facts, never invented."""
# ruff: noqa: RUF001, N812

from types import SimpleNamespace

import pytest

from shefa.pipeline import clinic_questions as Q
from shefa.pipeline import guided
from shefa.pipeline.replycheck import parrots, unsupported_claim
from shefa.pipeline.social import classify_social


@pytest.fixture
def clinic(tmp_path):
    from shefa.clinic import default as clinic_default
    from shefa.clinic.store import ClinicStore

    store = ClinicStore(tmp_path / "c.db")
    neuro = store.add_department("Neurology", "নিউরোলজি")
    gyn = store.add_department("Gynecology", "গাইনি")
    store.upsert_doctor(
        "Kabir",
        neuro,
        name_bn="কবির",
        qualification="MBBS, FCPS",
        profile={
            "designation": "Professor",
            "gender": "male",
            "languages": ["bn", "en"],
            "experience_years": 22,
        },
    )
    store.upsert_doctor(
        "Alam",
        neuro,
        name_bn="আলম",
        qualification="MBBS",
        profile={"designation": "Assistant Professor", "gender": "male"},
    )
    store.upsert_doctor(
        "Nahar",
        gyn,
        name_bn="নাহার",
        qualification="MBBS, FCPS",
        profile={"designation": "Associate Professor", "gender": "female"},
    )
    old = clinic_default._store
    clinic_default.set_default_clinic_store(store)
    yield store
    clinic_default.set_default_clinic_store(old)


def ask(said, session=None):
    return Q.answer(said, "bn", session or SimpleNamespace(metadata={}), {})


def test_who_is_best_recommends_the_most_senior_and_never_judges(clinic):
    reply = ask("নিউরোলজিতে কোন ডাক্তার সবচেয়ে ভালো?")
    assert "বিচার আমি করি না" in reply and "ডাক্তার কবির" in reply and "অধ্যাপক" in reply


def test_will_it_be_cured_is_for_the_doctor(clinic):
    reply = ask("ডাক্তার সাহেব কি ভালো? উনার কাছে গেলে কি রোগ সারবে?")
    assert "ডাক্তার দেখে বলবেন" in reply and "বিচার আমি করি না" in reply


def test_woman_doctor_comes_from_the_directory(clinic):
    reply = ask("মহিলা ডাক্তার আছে?")
    assert reply.startswith("জি, মহিলা ডাক্তার আছেন") and "নাহার" in reply and "কবির" not in reply
    assert ask("নিউরোলজিতে মহিলা ডাক্তার আছে?").startswith("না, এখানে এখন কোনো মহিলা ডাক্তার নেই")


def test_a_doctors_gender_languages_and_experience(clinic):
    assert "পুরুষ" in ask("ডাক্তার কবির কি ছেলে না মেয়ে?")
    assert "বাংলা ও ইংরেজিতে কথা বলেন" in ask("ডাক্তার কবির কি ইংরেজিতে কথা বলেন?")
    assert "২২" in ask("ডাক্তার কবির কত বছর ধরে, অভিজ্ঞ?") or "22" in ask(
        "ডাক্তার কবির কত বছর ধরে, অভিজ্ঞ?"
    )
    unclear = ask("ডাক্তার কি ছেলে না মেয়ে?")
    assert (
        unclear.startswith("কোন ডাক্তারের কথা বলছেন?") and "সিরিয়াল" not in unclear
    )  # one question back, no offer


def test_the_doctor_being_booked_is_the_context(clinic):
    kabir = next(d for d in clinic.doctors() if d["name_en"] == "Kabir")
    session = SimpleNamespace(metadata={"guided": {"step": "day", "doctor_id": kabir["id"]}})
    assert "পুরুষ" in Q.answer("উনি কি ছেলে না মেয়ে?", "bn", session, {}, during_booking=True)


@pytest.mark.parametrize(
    ("said", "topic"),
    [
        ("শুক্রবার খোলা?", "খোলার সময়"),
        ("আপনাদের ক্লিনিক কোথায়?", "ঠিকানা"),
        ("এমআরআই করা যায় এখানে?", "এমআরআই"),
        ("ভর্তি হতে চাই, সিট খালি আছে?", "ভর্তি"),
        ("আইসিইউ আছে আপনাদের?", "আইসিইউ"),
        ("আপনারা কি সরকারি না বেসরকারি?", "সরকারি"),
    ],
)
def test_clinic_facts_not_on_record_are_never_a_yes(clinic, said, topic):
    reply = ask(said)
    assert "নিশ্চিত তথ্য নেই" in reply and topic in reply and not reply.startswith("হ্যাঁ")


def test_clinic_facts_on_record_are_said_in_the_clinics_words(clinic):
    facts = {"hours": {"bn": "প্রতিদিন সকাল আটটা থেকে রাত দশটা খোলা, শুক্রবারও।"}}
    assert Q.answer("শুক্রবার খোলা?", "bn", SimpleNamespace(metadata={}), facts).startswith(
        "প্রতিদিন সকাল আটটা"
    )


def test_who_are_you(clinic):
    assert ask("আপনার নাম কী?").startswith("আমি SHEFA") and ask("আপনি কে?").startswith("আমি SHEFA")
    assert ask("আপনি কেমন আছেন?") is None  # "how are you" is not "who are you"


@pytest.mark.parametrize("said", ["কাল সকালে সিরিয়াল চাই", "আমার নাম রহিম", "০১৭১২৩৪৫৬৭৮", "ডাক্তার কবির"])
def test_booking_answers_are_left_alone(clinic, said):
    assert ask(said) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "হ্যাঁ, আমরা শুক্রবার খোলা।",
        "হ্যাঁ, অনেক মহিলা ডাক্তার আছে।",
        "আমরা একটি বেসরকারি ক্লিনিক।",
        "Yes, we have parking.",
    ],
)
def test_made_up_yes_answers_are_caught(sentence):
    assert unsupported_claim(sentence)


@pytest.mark.parametrize(
    "sentence", ["জি, বলুন।", "আমি একটি রোবট।", "কোন দিন আসতে চান?", "হ্যাঁ, বলুন কী সাহায্য লাগবে?"]
)
def test_ordinary_sentences_pass(sentence):
    assert not unsupported_claim(sentence)


def test_parroting_is_caught():
    assert parrots("আপনার নাম কী?", "আপনার নাম কী?") and not parrots("আমি SHEFA।", "আপনার নাম কী?")


def test_thanks_with_a_compliment_is_thanks():
    assert classify_social("ধন্যবাদ, আপনি অনেক ভালো") == "thanks"
    assert classify_social("আপনি কি মানুষ") is None


def test_showing_a_report_to_a_doctor_is_a_booking():
    assert guided.wants_to_book("আমার বাবার রিপোর্ট দেখাতে পারব?")


def test_english_answers_name_the_doctor(clinic):
    reply = Q.answer("who is the best doctor in neurology?", "en", SimpleNamespace(metadata={}), {})
    assert "Dr. Kabir" in reply


def test_a_service_question_names_the_department_that_sees_it(clinic):
    kabir = next(d for d in clinic.doctors() if d["name_en"] == "Kabir")
    clinic.upsert_doctor(
        "Kabir",
        kabir["department_id"],
        name_bn="কবির",
        profile={"designation": "Professor", "conditions": {"bn": ["মাথা ব্যথা"]}},
    )
    reply = ask("মাথা ব্যথার চিকিৎসা করেন?")
    assert reply.startswith("জি, এ জন্য নিউরোলজি বিভাগে") and "কবির" in reply
    assert ask("হার্টের অপারেশন করা যায়?") is None or "নিশ্চিত তথ্য নেই" in ask("হার্টের অপারেশন করা যায়?")
