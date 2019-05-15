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
				  topLinkCategory: category,
				  topTagCategory: "none",
				  bottomTagCategory: "POS",
                  showBottomMainLabel: false,
                  rowVerticalPadding: 2,
				}
			});
            basicTag.parser._parsedData.links.forEach((e) => {e.top = true})
            basicTag.redraw()
		}
		
		const $submitButton = $("#submitButton");
		
		$submitButton.click(async (e) => {
			e.preventDefault();
            
			const $sentenceInput = $("#sentenceInput");
			const response = await axios.post('/api/1/annotate', {sentence: $sentenceInput[0].value != "" ? $sentenceInput[0].value : "The quick brown fox jumped over the lazy dog."});
			
            $('#containerBasic').empty()
            $('#containerPlus').empty()
            
			displayTree(response.data.basic, "containerBasic", "universal-basic");
			displayTree(response.data.plus, "containerPlus", "universal-plus");
		});
	}
	
	return main;
});