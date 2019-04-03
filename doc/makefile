DOT_C=dot

DOTS=$(wildcard images/*.dot)
IMAGES=$(DOTS:.dot=.png)

build: $(IMAGES)

clean:
	rm -f $(IMAGES)

%.png : %.dot
	$(DOT_C) -Tpng $< -o $@

