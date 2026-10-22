<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/rss">
<html lang="en"><head>
 <meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
 <title><xsl:value-of select="channel/title"/></title>
 <style>
 *{box-sizing:border-box}body{margin:0;background:#f9f5f2;color:#392e34;font:400 15px/1.7 system-ui,-apple-system,"Segoe UI",sans-serif}a{color:#a52c3e}a:hover{text-decoration:underline}.container{max-width:900px;margin:0 auto;padding:48px 26px 90px}.brand{font:700 12px/1.4 system-ui;letter-spacing:2px;color:#9e3b51}.eyebrow{font-size:11px;letter-spacing:1.5px;font-weight:700;color:#a13d50;text-transform:uppercase;margin:38px 0 8px}h1{font:500 clamp(39px,6vw,66px)/1.1 Georgia,serif;letter-spacing:-1px;margin:14px 0 16px;max-width:800px}h2{font:500 25px/1.25 Georgia,serif;margin:0 0 10px}p{color:#64585e;margin:0 0 15px}.intro{font-size:16px;max-width:680px}.notice{background:#f0dfdc;border-left:3px solid #ad485b;padding:18px 22px;margin:28px 0 38px;font-size:13px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.actions a{background:#a52c3e;color:#fff;text-decoration:none;padding:11px 17px;font-size:12px;font-weight:700}.actions a.secondary{background:#fff;color:#a52c3e;border:1px solid #d9b7bd}.item{background:#fff;padding:24px 26px;margin:11px 0;border:1px solid #e8dcda}.item a{text-decoration:none}.item a:hover{text-decoration:underline}.item p{font-size:14px;line-height:1.72}.meta{font-size:10px;letter-spacing:1px;font-weight:700;color:#ad6975;text-transform:uppercase;margin-bottom:10px}.footer{font-size:12px;margin-top:32px;color:#786d70}@media(max-width:630px){.container{padding:28px 18px 56px}.item{padding:20px}.actions a{width:100%;text-align:center}}
 </style>
</head><body>
<main class="container">
 <div class="brand">ATTENTION / AI</div>
 <p class="eyebrow">RSS Feed</p>
 <h1><xsl:value-of select="channel/title"/></h1>
 <p class="intro"><xsl:value-of select="channel/description"/></p>
 <div class="notice">You're viewing an RSS feed in a browser. To follow updates automatically, copy this page's URL into an RSS reader. You can also read the latest edition directly on the site.</div>
 <div class="actions"><a href="subscribe.html">How to subscribe ↗</a><a class="secondary" href="./">Visit the Observatory ↗</a><a class="secondary" href="issues/">Published editions ↗</a></div>
 <p class="eyebrow">Available entries</p>
 <xsl:for-each select="channel/item">
  <article class="item">
   <p class="meta"><xsl:value-of select="pubDate"/></p>
   <h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
   <p><xsl:value-of select="description"/></p>
   <a href="{link}">Read the source or edition ↗</a>
  </article>
 </xsl:for-each>
 <p class="footer">A public research project exploring AI, attention, and human agency. Source links and dates remain available in the underlying RSS data.</p>
</main></body></html>
</xsl:template>
</xsl:stylesheet>