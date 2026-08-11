#!/usr/bin/env python3
"""Build platform_domains.txt: merged UGC hosts, deduped, grouped by category."""

from __future__ import annotations

import re
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "platform_domains.txt"
EXTRA = Path(__file__).resolve().parent / "platform_domains_extra.txt"

HEADER = """# PLATFORM_DOMAINS — company-owned or hosted platforms where people publish UGC
# (posts, profiles, comments, reviews, answers, wikis, channels, lists, map edits, etc.).
# Grouped by category; within each section hosts are sorted. eTLD+1 normalized where applicable.
# Excludes pure shopping-only, job boards, package CDNs, read-only aggregators.

"""


def etld1(host: str) -> str:
    parts = host.lower().split(".")
    if len(parts) < 2:
        return host.lower()
    if (
        len(parts) >= 3
        and parts[-2] in {"co", "com", "org", "net", "gov", "ac", "sch", "ne", "or", "go"}
        and len(parts[-1]) == 2
    ):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_valid_host(h: str) -> bool:
    h = h.strip().lower()
    if not h or h.startswith("#"):
        return False
    return bool(re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", h))


def parse_domain_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if is_valid_host(line):
            out.append(etld1(line))
    return out


def parse_categorized_extra(path: Path) -> tuple[list[str], dict[str, str]]:
    """Parse optional extra file: # === Category === lines assign following hosts."""
    if not path.exists():
        return [], {}
    order: list[str] = []
    assign: dict[str, str] = {}
    current = "Uncategorized (extra file)"
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            title = raw.lstrip("#").strip()
            if title.startswith("==="):
                title = title.strip("= ").strip()
            if title.lower().startswith("extra ugc"):
                continue
            current = title
            if current not in order:
                order.append(current)
            continue
        if is_valid_host(raw):
            h = etld1(raw)
            if h not in assign:
                assign[h] = current
    return order, assign


# Space/newline-separated tokens; script normalizes.
EXPANSION_BLOCK = r"""
xing.com nextdoor.com nextdoor.co.uk meetup.com mewe.com skyrock.com badoo.com twoo.com
hinge.co bumble.com tinder.com grindr.com scruff.com her.com feeld.co lovoo.com jdate.com
match.com okcupid.com plentyoffish.com zoosk.com eharmony.com raya.app innercircle.co
clubhouse.com strava.com alltrails.com komoot.com ridewithgps.com mapmyrun.com
myfitnesspal.com loseit.com cronometer.com fatsecret.com fitocracy.com jefit.com
letterboxd.com trakt.tv simkl.com tvtime.com justwatch.com reelgood.com
imdb.com metacritic.com rottentomatoes.com goodreads.com librarything.com bookcrossing.com
litsy.com thestorygraph.com serialreader.com
wattpad.com tapas.io webtoons.com tapastic.com inkitt.com royalroad.com fictionpress.com
fanfiction.net archiveofourown.org ao3.org sufficientvelocity.com spacebattles.com
questionablequesting.com scribblehub.com literotica.com storiesonline.net fiction.live
svbtle.com write.as bearblog.dev postach.io posthaven.com telegra.ph
dreamwidth.org insanejournal.com plurk.com friendica.net diasporafoundation.org
pixelfed.org joinpeertube.org bookwyrm.social kbin.social tildes.net snapzu.com saidit.net
lemmy.world lemmy.ml lemmy.ca lemmy.nz blahaj.zone programming.dev discuss.online lemm.ee
sopuli.xyz feddit.de lemmy.studio lemmy.today lemmy.zip midwest.social lemmygrad.ml
slrpnk.net hexbear.net beehaw.org lemmiereloaded.org lemmus.org mander.xyz
mastodon.social mastodon.online mstdn.social mastodon.art fosstodon.org hachyderm.io
infosec.exchange mstdn.jp pawoo.net mastodon.xyz mas.to qoto.org scientists.live
sigmoid.social universeodon.com techhub.social
guilded.gg steamcommunity.com steampowered.com roblox.com robloxdev.com minecraft.net
minecraftforum.net planetminecraft.com curseforge.com modrinth.com nexusmods.com mod.io
itch.io gamejolt.com newgrounds.com kongregate.com armor.games crazygames.com poki.com
miniclip.com addictinggames.com boardgamegeek.com faceit.com esea.net battle.net
flickr.com 500px.com unsplash.com pexels.com pixabay.com freepik.com vecteezy.com
flaticon.com thenounproject.com artstation.com cgsociety.org conceptart.org deviantart.com
coroflot.com carbonmade.com cargo.site smugmug.com zenfolio.com photoshelter.com picfair.com
eyeem.com youpic.com viewbug.com 1x.com photocrowd.com
bandcamp.com mixcloud.com audiomack.com hearthis.at reverbnation.com drooble.com
odysee.com lbry.com lbry.tv utreon.com floatplane.com nebula.tv viki.com vlive.tv
afreecatv.com sooplive.co.kr 17.live bigolive.tv tango.me likee.video kwai.com triller.co
firework.tv byte.co snackvideo.com vigo.live
circle.so mightynetworks.com skool.com kajabi.com thinkific.com teachable.com
podia.com gumroad.com patreon.com ko-fi.com buymeacoffee.com onlyfans.com fansly.com locals.com
subscribe.star
ask.fm curiouscat.me retrospring.net fluther.com blurtit.com answerbag.com fixya.com ifixit.com
alternativeto.net slant.co betalist.com saashub.com crozdesk.com financesonline.com
selecthub.com itcentralstation.com peerspot.com spiceworks.com
researchgate.net academia.edu zenodo.org figshare.com osf.io orcid.org biorxiv.org medrxiv.org
ssrn.com vixra.org philpapers.org deepdyve.com
observablehq.com rpubs.com kaggle.com deepnote.com hex.tech mode.com sigmaos.com
webflow.com framer.com readymag.com typedream.com dorik.com unicornplatform.com
micro.blog writefreely.org hubzilla.org socialhome.network peertube.tv
fc2.com fc2blog.us livedoor.com goo.ne.jp mixi.jp stand.fm voicy.jp
sharechat.com mojapp.com chingari.com kooapp.com roposo.com trell.co boloindya.com joshapp.com
mitron.tv helloapp.com kuaishou.com huaban.com acfun.cn huya.com douyu.com
wantedly.com connpass.com doorkeeper.jp peatix.com booth.pm fanbox.cc fantia.jp ci-en.net
viadeo.com openstreetmap.org wikimapia.org geni.com familysearch.org
wikibooks.org wikinews.org wikiquote.org wikisource.org wikiversity.org wikivoyage.org wiktionary.org
musicbrainz.org discogs.com themoviedb.org thetvdb.com anidb.net
myanimelist.net anilist.co kitsu.io ning.com invisioncommunity.com vanillaforums.com tribe.so
heartbeat.chat groups.io mobilizon.org calckey.world firefish.social akkoma.social gotosocial.org
misskey.io pleroma.social soapbox.pub
gitee.com coding.net segmentfault.com oschina.net v2ex.com cnblogs.com 51cto.com juejin.cn
infoq.com infoq.cn polywork.com contra.com about.me linktr.ee bio.link lnk.bio bento.me read.cv
chatgpt.com poe.com character.ai huggingface.co claude.ai perplexity.ai phind.com you.com
snap.com meta.com fb.com messenger.com
couchsurfing.com warmshowers.org bewelcome.org trustroots.org workaway.info helpx.net wwoof.net
forumotion.com forumer.com proboards.com freeforums.net tapatalk.com
inaturalist.org ebird.org zooniverse.org fold.it galaxyproject.org
lichess.org chess.com chess24.com internetchessclub.com
boardgamearena.com tabletopia.com roll20.net fantasygrounds.com foundryvtt.com astraltabletop.com
musescore.com ultimate-guitar.com songsterr.com chordify.net flat.io soundslice.com
genius.com musixmatch.com whosampled.com rateyourmusic.com albumoftheyear.org progarchives.com
discuss.elastic.co discuss.hashicorp.com discuss.kubernetes.io forum.golangbridge.org
ubuntuforums.org linuxquestions.org unix.com linuxmint.com
macrumors.com androidcentral.com xda-developers.com neowin.net hardforum.com overclock.net
guru3d.com tomshardware.com anandtech.com techpowerup.com linustechtips.com level1techs.com
slickdeals.net hotukdeals.com pepper.com mydealz.de dealabs.com retailmenot.com coupons.com
eventbrite.com luma.com partiful.com splashthat.com lu.ma mobilizon.org friendica.social
iceshrimp.dev sharkey.world catgirl.cloud
bogleheads.org early-retirement.org whitecoatinvestor.com fool.com seekingalpha.com stocktwits.com
elitetrader.com futures.io tradestation.com nasioc.com iwsti.com bimmerpost.com teslamotorsclub.com
electrek.co insideevs.com 9to5mac.com 9to5google.com arstechnica.com theverge.com
doctissimo.fr aufeminin.com netmums.com mumsnet.com babycenter.com allnurses.com
thestudentroom.co.uk studentdoctor.net physicsforums.com biology-online.org mymathforum.com
my.opera.com jeuxvideo.com jvc.gg onvasortir.com cafemom.com circleofmoms.com
"""


def tokenize(block: str) -> list[str]:
    return [t.strip().lower() for t in block.replace("\n", " ").split() if t.strip()]


# Ordered rules: first match wins. Used when host not in EXTRA assign map.
def category_for(h: str) -> str:
    if h.endswith(".social") and h not in ("truth.social",):
        return "Fediverse & decentralized social"
    if "lemmy" in h or h.startswith("lemm.") or "feddit" in h:
        return "Fediverse & decentralized social"
    if "mastodon" in h or "mstdn" in h or h.endswith("odon.com"):
        return "Fediverse & decentralized social"
    if any(
        x in h
        for x in (
            "pleroma",
            "pixelfed",
            "peertube",
            "akkoma",
            "calckey",
            "misskey",
            "gotosocial",
            "kbin",
            "bookwyrm",
            "firefish",
            "iceshrimp",
            "sharkey",
            "soapbox",
            "friendica",
            "diaspora",
            "hubzilla",
            "socialhome",
            "fosstodon",
            "hachyderm",
            "infosec.exchange",
            "pawoo",
            "joinpeertube",
            "writefreely",
            "mobilizon",
            "snapzu",
            "tildes.net",
            "programming.dev",
            "discuss.online",
            "beehaw",
            "hexbear",
            "blahaj",
            "mander.xyz",
            "lemmus.org",
            "lemmiereloaded",
            "sopuli",
            "slrpnk",
            "midwest.social",
            "catgirl.cloud",
            "nostr",
            "cohost.org",
        )
    ):
        return "Fediverse & decentralized social"
    if h in ("matrix.org", "element.io", "signal.org", "wire.com", "zulip.com", "rocket.chat"):
        return "Messaging & chat"
    if h in (
        "twitter.com",
        "x.com",
        "facebook.com",
        "fb.com",
        "instagram.com",
        "threads.net",
        "bsky.app",
        "bluesky.app",
        "linkedin.com",
        "pinterest.com",
        "reddit.com",
        "tumblr.com",
        "vk.com",
        "weibo.com",
        "qq.com",
        "tiktok.com",
        "snap.com",
        "snapchat.com",
        "meta.com",
        "messenger.com",
        "whatsapp.com",
        "telegram.org",
        "t.me",
        "discord.com",
        "slack.com",
        "line.me",
        "kakao.com",
        "viber.com",
        "wechat.com",
        "truth.social",
        "spoutible.com",
        "gettr.com",
        "parler.com",
        "gab.com",
        "minds.com",
        "post.news",
        "nextdoor.com",
        "nextdoor.co.uk",
        "xing.com",
        "viadeo.com",
    ):
        return "Major social & profiles"
    if h in (
        "tinder.com",
        "bumble.com",
        "hinge.co",
        "grindr.com",
        "scruff.com",
        "her.com",
        "feeld.co",
        "badoo.com",
        "twoo.com",
        "lovoo.com",
        "jdate.com",
        "match.com",
        "okcupid.com",
        "plentyoffish.com",
        "zoosk.com",
        "eharmony.com",
        "raya.app",
        "innercircle.co",
    ):
        return "Dating"
    if h in (
        "meetup.com",
        "eventbrite.com",
        "luma.com",
        "lu.ma",
        "partiful.com",
        "splashthat.com",
        "peatix.com",
        "doorkeeper.jp",
        "connpass.com",
        "couchsurfing.com",
        "warmshowers.org",
        "bewelcome.org",
        "trustroots.org",
        "workaway.info",
        "wwoof.net",
        "helpx.net",
        "clubhouse.com",
    ):
        return "Meetups & travel communities"
    if h in (
        "youtube.com",
        "youtu.be",
        "twitch.tv",
        "vimeo.com",
        "dailymotion.com",
        "rumble.com",
        "bitchute.com",
        "odysee.com",
        "kick.com",
        "floatplane.com",
        "nebula.tv",
        "dlive.tv",
        "bilibili.com",
        "nicovideo.jp",
        "afreecatv.com",
        "sooplive.co.kr",
        "17.live",
        "bigolive.tv",
        "tango.me",
        "likee.video",
        "kwai.com",
        "triller.co",
        "firework.tv",
        "byte.co",
        "snackvideo.com",
        "vigo.live",
        "vlive.tv",
        "viki.com",
        "utreon.com",
        "lbry.com",
        "lbry.tv",
    ):
        return "Video & live streaming"
    if h in (
        "spotify.com",
        "soundcloud.com",
        "bandcamp.com",
        "mixcloud.com",
        "audiomack.com",
        "hearthis.at",
        "reverbnation.com",
        "drooble.com",
        "anchor.fm",
        "buzzsprout.com",
        "simplecast.com",
        "transistor.fm",
        "redcircle.com",
        "podbean.com",
        "megaphone.fm",
        "castbox.fm",
        "libsyn.com",
    ):
        return "Music, podcasts & audio"
    if h in (
        "steamcommunity.com",
        "steampowered.com",
        "roblox.com",
        "robloxdev.com",
        "minecraft.net",
        "minecraftforum.net",
        "planetminecraft.com",
        "curseforge.com",
        "modrinth.com",
        "nexusmods.com",
        "mod.io",
        "itch.io",
        "gamejolt.com",
        "newgrounds.com",
        "kongregate.com",
        "armor.games",
        "crazygames.com",
        "poki.com",
        "miniclip.com",
        "addictinggames.com",
        "faceit.com",
        "esea.net",
        "battle.net",
        "guilded.gg",
        "gather.town",
    ):
        return "Games & mods"
    if h in (
        "boardgamegeek.com",
        "boardgamearena.com",
        "tabletopia.com",
        "roll20.net",
        "fantasygrounds.com",
        "foundryvtt.com",
        "astraltabletop.com",
        "lichess.org",
        "chess.com",
        "chess24.com",
        "internetchessclub.com",
    ):
        return "Board, tabletop & chess"
    if h in (
        "quora.com",
        "zhihu.com",
        "stackoverflow.com",
        "stackexchange.com",
    ):
        return "Q&A & knowledge communities"
    if h in (
        "stackblitz.com",
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "sourceforge.net",
        "codeberg.org",
        "sr.ht",
        "replit.com",
        "glitch.com",
        "codepen.io",
        "jsfiddle.net",
        "codesandbox.io",
        "gitee.com",
        "launchpad.net",
        "gitpod.io",
    ) or h.endswith("kubernetes.io"):
        return "Developer tools & code hosting"
    if h in (
        "ask.fm",
        "curiouscat.me",
        "retrospring.net",
        "fluther.com",
        "blurtit.com",
        "answerbag.com",
    ):
        return "Q&A & casual asks"
    if h in (
        "yelp.com",
        "tripadvisor.com",
        "trustpilot.com",
        "sitejabber.com",
        "trustradius.com",
        "g2.com",
        "capterra.com",
        "getapp.com",
        "softwareadvice.com",
        "glassdoor.com",
        "wellfound.com",
        "angel.co",
    ):
        return "Reviews & business reputation"
    if h in (
        "wikipedia.org",
        "wikimedia.org",
        "wikidata.org",
        "wikibooks.org",
        "wikinews.org",
        "wikiquote.org",
        "wikisource.org",
        "wikiversity.org",
        "wikivoyage.org",
        "wiktionary.org",
        "scholarpedia.org",
        "citizendium.org",
        "fandom.com",
        "wikia.com",
        "miraheze.org",
        "wikidot.com",
        "wiki.gg",
    ):
        return "Wikis & reference"
    if h in (
        "medium.com",
        "substack.com",
        "ghost.io",
        "beehiiv.com",
        "buttondown.email",
        "wordpress.com",
        "blogspot.com",
        "blogger.com",
        "tistory.com",
        "typepad.com",
        "squarespace.com",
        "wix.com",
        "weebly.com",
        "strikingly.com",
        "telegra.ph",
        "svbtle.com",
        "write.as",
        "micro.blog",
        "bearblog.dev",
        "postach.io",
        "posthaven.com",
        "wattpad.com",
        "tapas.io",
        "tapastic.com",
        "webtoons.com",
        "inkitt.com",
        "royalroad.com",
        "fictionpress.com",
        "fanfiction.net",
        "archiveofourown.org",
        "ao3.org",
        "sufficientvelocity.com",
        "spacebattles.com",
        "questionablequesting.com",
        "scribblehub.com",
        "literotica.com",
        "storiesonline.net",
        "fiction.live",
        "dreamwidth.org",
        "insanejournal.com",
        "livejournal.com",
        "plurk.com",
        "skyrock.com",
        "ameblo.jp",
        "note.com",
        "hatena.ne.jp",
        "lineblog.me",
        "fc2.com",
        "fc2blog.us",
        "livedoor.com",
        "goo.ne.jp",
    ):
        return "Publishing, blogs & fanfiction"
    if h in (
        "goodreads.com",
        "librarything.com",
        "bookcrossing.com",
        "litsy.com",
        "thestorygraph.com",
        "serialreader.com",
        "bookmeter.com",
        "kakuyomu.jp",
    ):
        return "Books & reading"
    if h in (
        "imdb.com",
        "metacritic.com",
        "rottentomatoes.com",
        "themoviedb.org",
        "thetvdb.com",
        "anidb.net",
        "myanimelist.net",
        "anilist.co",
        "kitsu.io",
        "letterboxd.com",
        "trakt.tv",
        "simkl.com",
        "tvtime.com",
        "justwatch.com",
        "reelgood.com",
        "musicbrainz.org",
        "discogs.com",
        "albumoftheyear.org",
        "rateyourmusic.com",
        "progarchives.com",
        "genius.com",
        "musixmatch.com",
        "whosampled.com",
        "musescore.com",
        "ultimate-guitar.com",
        "songsterr.com",
        "chordify.net",
        "flat.io",
        "soundslice.com",
    ):
        return "Film, TV & music metadata"
    if h in (
        "flickr.com",
        "500px.com",
        "unsplash.com",
        "pexels.com",
        "pixabay.com",
        "freepik.com",
        "vecteezy.com",
        "flaticon.com",
        "thenounproject.com",
        "artstation.com",
        "cgsociety.org",
        "conceptart.org",
        "deviantart.com",
        "pixiv.net",
        "tinami.jp",
        "behance.net",
        "dribbble.com",
        "coroflot.com",
        "carbonmade.com",
        "cargo.site",
        "smugmug.com",
        "zenfolio.com",
        "photoshelter.com",
        "picfair.com",
        "eyeem.com",
        "youpic.com",
        "viewbug.com",
        "1x.com",
        "photocrowd.com",
        "canva.com",
        "figma.com",
        "webflow.com",
        "framer.com",
        "readymag.com",
        "typedream.com",
        "dorik.com",
        "unicornplatform.com",
    ):
        return "Photos, art & design"
    if h in (
        "strava.com",
        "alltrails.com",
        "komoot.com",
        "ridewithgps.com",
        "mapmyrun.com",
        "myfitnesspal.com",
        "loseit.com",
        "cronometer.com",
        "fatsecret.com",
        "fitocracy.com",
        "jefit.com",
        "bodybuilding.com",
    ):
        return "Fitness & outdoor tracking"
    if h in (
        "openstreetmap.org",
        "wikimapia.org",
        "inaturalist.org",
        "ebird.org",
        "zooniverse.org",
        "fold.it",
        "galaxyproject.org",
    ):
        return "Maps & citizen science"
    if h in (
        "researchgate.net",
        "academia.edu",
        "zenodo.org",
        "figshare.com",
        "osf.io",
        "orcid.org",
        "biorxiv.org",
        "medrxiv.org",
        "ssrn.com",
        "vixra.org",
        "philpapers.org",
        "deepdyve.com",
    ):
        return "Research & preprints"
    if h in (
        "observablehq.com",
        "rpubs.com",
        "kaggle.com",
        "deepnote.com",
        "hex.tech",
        "mode.com",
        "sigmaos.com",
    ):
        return "Data science & notebooks"
    if h in (
        "bogleheads.org",
        "early-retirement.org",
        "whitecoatinvestor.com",
        "fool.com",
        "seekingalpha.com",
        "stocktwits.com",
        "elitetrader.com",
        "futures.io",
        "tradestation.com",
    ):
        return "Finance & investing forums"
    if h in (
        "nasioc.com",
        "iwsti.com",
        "bimmerpost.com",
        "teslamotorsclub.com",
        "electrek.co",
        "insideevs.com",
        "macrumors.com",
        "androidcentral.com",
        "xda-developers.com",
        "neowin.net",
        "hardforum.com",
        "overclock.net",
        "guru3d.com",
        "tomshardware.com",
        "anandtech.com",
        "techpowerup.com",
        "linustechtips.com",
        "level1techs.com",
        "9to5mac.com",
        "9to5google.com",
        "arstechnica.com",
        "theverge.com",
        "slickdeals.net",
        "hotukdeals.com",
        "pepper.com",
        "mydealz.de",
        "dealabs.com",
        "retailmenot.com",
        "coupons.com",
    ):
        return "Tech media & enthusiast forums"
    if h in (
        "doctissimo.fr",
        "aufeminin.com",
        "netmums.com",
        "mumsnet.com",
        "babycenter.com",
        "allnurses.com",
        "thestudentroom.co.uk",
        "studentdoctor.net",
        "physicsforums.com",
        "biology-online.org",
        "mymathforum.com",
        "cafemom.com",
        "circleofmoms.com",
        "jeuxvideo.com",
        "jvc.gg",
        "onvasortir.com",
    ):
        return "Health, parenting & student forums"
    if h in (
        "alternativeto.net",
        "slant.co",
        "betalist.com",
        "saashub.com",
        "crozdesk.com",
        "financesonline.com",
        "selecthub.com",
        "itcentralstation.com",
        "peerspot.com",
        "spiceworks.com",
        "producthunt.com",
    ):
        return "Software directories & B2B reviews"
    if h in (
        "patreon.com",
        "gumroad.com",
        "ko-fi.com",
        "buymeacoffee.com",
        "onlyfans.com",
        "fansly.com",
        "locals.com",
        "subscribe.star",
        "circle.so",
        "mightynetworks.com",
        "skool.com",
        "kajabi.com",
        "thinkific.com",
        "teachable.com",
        "podia.com",
    ):
        return "Creator economy & courses"
    if h in (
        "geni.com",
        "familysearch.org",
        "fixya.com",
        "ifixit.com",
    ):
        return "How-to, repairs & genealogy"
    if h in (
        "ning.com",
        "invisioncommunity.com",
        "vanillaforums.com",
        "tribe.so",
        "heartbeat.chat",
        "groups.io",
        "proboards.com",
        "freeforums.net",
        "forumotion.com",
        "forumer.com",
        "tapatalk.com",
        "ubuntuforums.org",
        "linuxquestions.org",
        "unix.com",
        "linuxmint.com",
        "resetera.com",
        "neogaf.com",
        "somethingawful.com",
        "slashdot.org",
        "lobste.rs",
        "ycombinator.com",
        "hubski.com",
        "saidit.net",
        "dzone.com",
    ):
        return "Forums & discussion boards"
    if h.startswith("discuss.") or h in (
        "forum.golangbridge.org",
        "golangbridge.org",
    ):
        return "Project forums & discuss.*"
    if h in (
        "baidu.com",
        "naver.com",
        "daum.net",
        "douban.com",
        "xiaohongshu.com",
        "sharechat.com",
        "mojapp.com",
        "chingari.com",
        "kooapp.com",
        "roposo.com",
        "trell.co",
        "boloindya.com",
        "joshapp.com",
        "mitron.tv",
        "helloapp.com",
        "kuaishou.com",
        "huaban.com",
        "acfun.cn",
        "huya.com",
        "douyu.com",
        "douyin.com",
        "wantedly.com",
        "fanbox.cc",
        "booth.pm",
        "fantia.jp",
        "ci-en.net",
        "stand.fm",
        "voicy.jp",
        "mixi.jp",
        "v2ex.com",
        "cnblogs.com",
        "51cto.com",
        "juejin.cn",
        "infoq.com",
        "infoq.cn",
        "segmentfault.com",
        "oschina.net",
        "coding.net",
    ):
        return "Regional & language-specific communities"
    if h in (
        "polywork.com",
        "contra.com",
        "about.me",
        "linktr.ee",
        "bio.link",
        "lnk.bio",
        "bento.me",
        "read.cv",
        "carrd.co",
        "notion.so",
        "coda.io",
        "dropboxpaper.com",
        "hackmd.io",
        "hackmd.com",
        "etherpad.org",
        "cryptpad.fr",
        "jimdo.com",
    ):
        return "Profiles, link-in-bio & docs"
    if h in (
        "chatgpt.com",
        "poe.com",
        "character.ai",
        "huggingface.co",
        "claude.ai",
        "perplexity.ai",
        "phind.com",
        "you.com",
    ):
        return "AI assistants & ML hubs"
    if h in (
        "my.opera.com",
        "opera.com",
    ):
        return "Miscellaneous UGC & communities"
    return "Miscellaneous UGC & communities"


# Canonical order for section headers in the output file
CATEGORY_ORDER = [
    "Fediverse & decentralized social",
    "Major social & profiles",
    "Messaging & chat",
    "Dating",
    "Meetups & travel communities",
    "Forums & discussion boards",
    "Project forums & discuss.*",
    "Q&A & knowledge communities",
    "Q&A & casual asks",
    "Reviews & business reputation",
    "Software directories & B2B reviews",
    "Developer tools & code hosting",
    "Data science & notebooks",
    "Publishing, blogs & fanfiction",
    "Books & reading",
    "Wikis & reference",
    "Film, TV & music metadata",
    "Photos, art & design",
    "Music, podcasts & audio",
    "Video & live streaming",
    "Games & mods",
    "Board, tabletop & chess",
    "Fitness & outdoor tracking",
    "Maps & citizen science",
    "Research & preprints",
    "Finance & investing forums",
    "Tech media & enthusiast forums",
    "Health, parenting & student forums",
    "Creator economy & courses",
    "Profiles, link-in-bio & docs",
    "How-to, repairs & genealogy",
    "Regional & language-specific communities",
    "AI assistants & ML hubs",
    "Miscellaneous UGC & communities",
]


def main() -> None:
    baseline = parse_domain_lines(OUT) if OUT.exists() else []
    _, extra_assign = parse_categorized_extra(EXTRA)

    seen: set[str] = set()

    def add(h: str) -> None:
        if not is_valid_host(h):
            return
        seen.add(etld1(h))

    for h in baseline:
        add(h)
    for h in tokenize(EXPANSION_BLOCK):
        add(h)

    buckets: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
    if "Uncategorized (extra file)" not in buckets:
        buckets["Uncategorized (extra file)"] = []

    for h in sorted(seen):
        cat = extra_assign.get(h) or category_for(h)
        if cat not in buckets:
            buckets[cat] = []
        buckets[cat].append(h)

    lines: list[str] = [HEADER.rstrip("\n")]
    for cat in CATEGORY_ORDER:
        hosts = sorted(set(buckets.get(cat, [])))
        if not hosts:
            continue
        lines.append(f"# === {cat} ===")
        lines.extend(hosts)
        lines.append("")
    # Any categories not in CATEGORY_ORDER (from extra file)
    for cat, hosts in sorted(buckets.items()):
        if cat in CATEGORY_ORDER or cat == "Uncategorized (extra file)":
            continue
        if not hosts:
            continue
        lines.append(f"# === {cat} ===")
        lines.extend(sorted(set(hosts)))
        lines.append("")
    extra_left = buckets.get("Uncategorized (extra file)", [])
    if extra_left:
        lines.append("# === Uncategorized (extra file) ===")
        lines.extend(sorted(set(extra_left)))
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} with {len(seen)} unique domains in {len([c for c in CATEGORY_ORDER if buckets.get(c)])} primary categories")


if __name__ == "__main__":
    main()
