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
                basicTag.links.forEach((e) => {
                    found = false
                    links.forEach((e2) => {
                        if ((e2.arguments[0].anchor.text == e.arguments[0].anchor.text) && (e2.trigger.text == e.trigger.text))
                        {
                            found = true
                            if (e2.reltype != e.reltype)
                            {
                                e.svg.node.style.fill = "#FF7800"
                                e2.svg.node.style.fill = "#FF7800"
                            }
                        }
                    })

                    if (found == false)
                    {
                        e.svg.node.style.fill = "#00FF00"
                        basicTag.links.forEach((e3) => {
                            if ((e != e3) && ((((e3.arguments[0].anchor.text == e.arguments[0].anchor.text) && (e3.trigger.text == e.trigger.text))) || (((e3.arguments[0].anchor.text == e.trigger.text) && (e3.trigger.text == e.arguments[0].anchor.text)))))
                            {
                                e.top = false
                                e.slot = e.slot * -1
                                e.show()
                                basicTag.resize()
                            }
                        })
                    }
                    
                })
                links.forEach((e) => {
                    found = false
                    basicTag.links.forEach((e2) => {
                        if ((e2.arguments[0].anchor.text == e.arguments[0].anchor.text) && (e2.trigger.text == e.trigger.text))
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
            
			const $sentenceInput = $("#sentenceInput");
			const response = await axios.post('/api/1/annotate', {sentence: $sentenceInput[0].value != "" ? $sentenceInput[0].value : "The quick brown fox jumped over the lazy dog."});
			
            $('#containerBasic').empty()
            $('#containerPlus').empty()
            
			tag1 = displayTree(response.data.basic, "containerBasic", "universal-basic");
			tag2 = displayTree(response.data.plus, "containerPlus", "universal-plus", tag1.links);
		});
	}
	
	return main;
});