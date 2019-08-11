define([
	'jquery', 
	'tag',
	'axios',
], function(
	$, 
	TAG,
	axios,
) {
	
	// -------------
	// Basic example
	// -------------
	function main() {
		
		function displayTree(data, containerId, category) {
			var links = arguments.length > 3 && arguments[3] !== undefined ? arguments[3] : [];
            const container = $('#' + containerId);
			const basicTag = TAG.tag({
				// The `container` parameter can take either the ID of the main element or
				// the main element itself (as either a jQuery or native object)
				container: container,

				// The initial data to load.
				// Different formats might expect different types for `data`:
				// sE.g., the "odin" format expects the annotations as an
				// (already-parsed) Object, while the "brat" format expects them as a raw
				// String.
				// See the full documentation for details.
				data: data,
				format: "odin",

				// Overrides for default options
				options: {
				  showTopMainLabel: true,
                  showTopLinksOnMove: true,
				  showTopArgLabels: false,
				  showBottomMainLabel: true,
                  showBottomLinksOnMove: true,
				  showBottomArgLabels: false,
				  topLinkCategory: category,
				  BottomLinkCategory: category,
				  topTagCategory: "none",
				  bottomTagCategory: "POS",
                  //rowVerticalPadding: 2,
                  compactRows: true,
                  
				}
			});
            basicTag.parser._parsedData.links.forEach((e) => {e.top = true})
            basicTag.redraw()
            if (links.length > 0)
            {
				// find the shift when word amount is changed.
				var shifts = {};
				var pointer1 = 0;
				var pointer2 = 0;
				while (pointer1 < links[0].main.words.length)
				{
					shifts[pointer2] = pointer1
					if (links[0].main.words[pointer1].text == basicTag.links[0].main.words[pointer2].text)
					{ 
						pointer1++;
					}
					else
					{
						shifts[pointer2] -= 0.9
					}
					pointer2++;
				}
				
				var dict = {};
                basicTag.links.forEach((e) => {
                    found = false
                    links.forEach((e2) => {
                        if ((e2.arguments[0].anchor.idx == shifts[e.arguments[0].anchor.idx]) && (((e.trigger in window) && (e2.trigger in window)) || ((!(e.trigger in window)) && (!(e2.trigger in window)) && (e2.trigger.idx == shifts[e.trigger.idx]))))
                        {
                            found = true
                            if (e2.reltype != e.reltype)
                            {
                                e.svg.node.style.fill = "#FFAA00"
                                e2.svg.node.style.fill = "#FFAA00"
                            }
                        }
                    })

                    if (found == false)
                    {
						var other = -1
						if (!(e.trigger in window))
						{
							other = e.trigger.idx
						}
						var min = Math.min(e.arguments[0].anchor.idx, other)
						var max = Math.max(e.arguments[0].anchor.idx, other)
						pair = [min, max]
						
                        var clash = false
						e.svg.node.style.fill = "#00FF00"
                        if (pair in dict)
						{
							clash = true
							dict[pair] -= 1
						}
						else
						{
							basicTag.links.every((e3) => {
								if ((e != e3) && ((((shifts[e3.arguments[0].anchor.idx] == shifts[e.arguments[0].anchor.idx]) && (((e.trigger in window) && (e3.trigger in window)) || ((!(e.trigger in window)) && (!(e3.trigger in window)) && (shifts[e3.trigger.idx] == shifts[e.trigger.idx])))) || (((!(e.trigger in window)) && (!(e3.trigger in window)) && (shifts[e3.arguments[0].anchor.idx] == shifts[e.trigger.idx]) && (shifts[e3.trigger.idx] == shifts[e.arguments[0].anchor.idx]))))))
								{
									clash = true
									dict[pair] = -1
									return false;
								}
								return true;
							})
						}
                        if (clash == true)
                        {
                            e.top = false
							e.slot = dict[pair]
                            e.show()
                            basicTag.resize()	
                        }
                    }
                    
                })
                links.forEach((e) => {
                    found = false
                    basicTag.links.forEach((e2) => {
                        if ((shifts[e2.arguments[0].anchor.idx] == e.arguments[0].anchor.idx) && (((e.trigger in window) && (e2.trigger in window)) || ((!(e.trigger in window)) && (!(e2.trigger in window)) && (shifts[e2.trigger.idx] == e.trigger.idx))))
                        {
                            found = true
                        }
                    })

                    if (found == false)
                    {
                        e.svg.node.style.fill = "#FF0000"
                    }
                })
            }
            return basicTag
		}
		
		const $submitButton = $("#submitButton");
		
		$submitButton.click(async (e) => {
			e.preventDefault();
			var eUd = document.getElementById("GFG1").checked
			var eUdPP = document.getElementById("GFG2").checked
			var eUdAryeh = document.getElementById("GFG3").checked
			const $sentenceInput = $("#sentenceInput");
            $sentenceInput[0].value = $sentenceInput[0].value != "" ? $sentenceInput[0].value : "The quick brown fox jumped over the lazy dog."
			const response = await axios.post('/api/1/annotate', {sentence: $sentenceInput[0].value, eud: eUd, eud_pp: eUdPP, eud_aryeh: eUdAryeh});
			
            $('#containerBasic').empty()
            $('#containerPlus').empty()
            
			tag1 = displayTree(response.data.basic, "containerBasic", "universal-basic");
			tag2 = displayTree(response.data.plus, "containerPlus", "universal-aryeh", tag1.links);
		});
        
        var slash_idx = window.location.href.lastIndexOf('/')
        if ((slash_idx + 1) != window.location.href.length)
        {
            sliced = window.location.href.slice(slash_idx + 1)
            $("#sentenceInput")[0].value = decodeURIComponent(sliced)
            submitButton.click(this);
        }
	}
	
	return main;
});
