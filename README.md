# google-poi-japan

Codes for the extraction of POI data in Japan

## Briefing

- See general documentation about Places API at https://developers.google.com/maps/documentation/places/web-service/overview?hl=zh-cn#places-api-new
- See Places API instruction about the places.types and .primarytypes at https://developers.google.com/maps/documentation/places/web-service/place-types?hl=zh-cn
- Use `/api/place/details` to get details of a place containing prices and ratings data at https://developers.google.com/maps/documentation/places/web-service/details?hl=zh-cn
- Use `/api/place/nearbysearch` to get list of results near a point at https://developers.google.com/maps/documentation/places/web-service/search-nearby?hl=zh-cn
- See supported types for searching at https://developers.google.com/maps/documentation/places/web-service/supported_types?hl=zh-cn
- Alternative: use DATAFORSEO's API service at https://docs.dataforseo.com/v3/serp/google/maps/overview/?python
- Use advanced nearbysearch services ($35/1,000 times): https://developers.google.com/maps/documentation/places/web-service/usage-and-billing?hl=zh-cn#advanced-nearbysearch
- Use SerpApi local search for POIs at https://serpapi.com/google-local-api

## Facts

- 45 odakyu sites in total.
- 96 primary types of POIs from Google Map.
- Only 1 type can be specified per request.
- Only 20 results will be returned per request and 60 results maximum from Google Map APIs.
- 6,000 searches in a month for nearbysearch yield no charge (see https://mapsplatform.google.com/pricing/?hl=zh-cn&_gl=1%2Atuvq1w%2A_ga%2AMTc5MzI2MjI0NC4xNzEwNzUyODgx%2A_ga_NRWSTWS78N%2AMTcxMDc1MzgwMy4xLjEuMTcxMDc1NzY3OC4wLjAuMA..#pricing-grid).
- SerpApi offers 20 results with pagination from Places Search (demo https://serpapi.com/playground?engine=google_local&q=Restaurants&location=Sagamihara%2C+Kanagawa+Prefecture%2C+Japan&google_domain=google.co.jp&gl=jp&hl=ja&start=20)

## Quick Start

Make sure you have properly set up the API project and fetched the API keys with enough allowances. Then you can start 
with the script `google.py` to scrape down the data. 

## TODO

- [x] run a demo script for Google Map API
- [x] fetch the first batch of restaurant POIs and estimate how much will it cost
- [x] check how `fields` work in the query and how many results we will usually get
- [x] add serpapi based codes for places crawling
- [x] save api results in `sqlite` with its query and response as a `cache`
- [ ] price information needs bug fixing waiting for SerpApi team's response